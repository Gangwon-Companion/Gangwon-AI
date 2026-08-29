from __future__ import annotations

from collections import Counter
from datetime import datetime
from enum import StrEnum
from typing import Literal

from app.core.state import (
    AgentName,
    ItinerarySlot,
    QualityIssue,
    QualityValidationResult,
    TravelState,
    ValidationAction,
)


class QualityIssueType(StrEnum):
    ROUTE_INEFFICIENCY = "ROUTE_INEFFICIENCY"
    SCHEDULE_TOO_TIGHT = "SCHEDULE_TOO_TIGHT"
    MEAL_TIME_INAPPROPRIATE = "MEAL_TIME_INAPPROPRIATE"
    CATEGORY_REPETITION = "CATEGORY_REPETITION"
    PREFERENCE_UNDERREFLECTED = "PREFERENCE_UNDERREFLECTED"
    TRIP_PURPOSE_UNCLEAR = "TRIP_PURPOSE_UNCLEAR"


_CATEGORY_AGENT: dict[str, AgentName] = {
    "DESTINATION": "destination",
    "RESTAURANT": "restaurant",
    "LODGING": "lodging",
}


def _start_hour(item: ItinerarySlot) -> float | None:
    try:
        value = datetime.fromisoformat(item["start_at"])
    except (KeyError, ValueError):
        return None
    return value.hour + value.minute / 60


def _issue(
    issue_type: QualityIssueType,
    slots: list[str],
    reason: str,
    severity: Literal["MINOR", "MAJOR"] = "MAJOR",
) -> QualityIssue:
    return {
        "type": issue_type.value,
        "severity": severity,
        "slots": slots,
        "reason": reason,
    }


def _evaluate_route(itinerary: list[ItinerarySlot]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for previous, current in zip(itinerary, itinerary[1:]):
        travel = current.get("travel_minutes_from_previous")
        if travel is not None and travel > 90:
            issues.append(
                _issue(
                    QualityIssueType.ROUTE_INEFFICIENCY,
                    [previous.get("slot", "UNKNOWN"), current.get("slot", "UNKNOWN")],
                    f"연속된 두 장소의 이동시간이 {travel}분으로 과도합니다.",
                )
            )
    return issues


def _evaluate_pacing(itinerary: list[ItinerarySlot]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for previous, current in zip(itinerary, itinerary[1:]):
        try:
            previous_end = datetime.fromisoformat(previous["end_at"])
            current_start = datetime.fromisoformat(current["start_at"])
        except (KeyError, ValueError):
            continue
        travel = current.get("travel_minutes_from_previous", 0)
        rest_minutes = (current_start - previous_end).total_seconds() / 60 - travel
        if 0 <= rest_minutes < 10:
            issues.append(
                _issue(
                    QualityIssueType.SCHEDULE_TOO_TIGHT,
                    [previous.get("slot", "UNKNOWN"), current.get("slot", "UNKNOWN")],
                    f"이동 후 여유 시간이 {rest_minutes:.0f}분뿐입니다.",
                    "MINOR",
                )
            )
    return issues


def _evaluate_meals(itinerary: list[ItinerarySlot]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for item in itinerary:
        slot = item.get("slot", "")
        hour = _start_hour(item)
        if hour is None:
            continue
        is_lunch = slot.endswith("_LUNCH")
        is_dinner = slot.endswith("_DINNER")
        if (is_lunch and not 11 <= hour <= 14) or (is_dinner and not 17 <= hour <= 20.5):
            issues.append(
                _issue(
                    QualityIssueType.MEAL_TIME_INAPPROPRIATE,
                    [slot],
                    "식사 시작 시간이 권장 시간대를 크게 벗어납니다.",
                )
            )
    return issues


def _evaluate_repetition(itinerary: list[ItinerarySlot]) -> list[QualityIssue]:
    experiential = [
        item for item in itinerary if item.get("category") not in {"RESTAURANT", "LODGING"}
    ]
    tags = [item.get("tags", [""])[0] if item.get("tags") else "" for item in experiential]
    counts = Counter(tag for tag in tags if tag)
    repeated = [tag for tag, count in counts.items() if count >= 3]
    if not repeated:
        return []
    slots = [
        item.get("slot", "UNKNOWN")
        for item in experiential
        if set(item.get("tags", [])) & set(repeated)
    ]
    return [
        _issue(
            QualityIssueType.CATEGORY_REPETITION,
            slots,
            f"동일 경험 유형({', '.join(repeated)})이 세 번 이상 반복됩니다.",
            "MINOR",
        )
    ]


def _evaluate_preferences(state: TravelState) -> list[QualityIssue]:
    preferences = set(state.get("preference_profile", {}).get("keywords", []))
    if not preferences:
        return []
    itinerary = state.get("itinerary", [])
    normalized = set(state.get("preference_profile", {}).get("soft", {}))
    expected = preferences | normalized
    matched = expected & {
        tag for item in itinerary for tag in item.get("tags", [])
    }
    ratio = len(matched) / len(expected)
    if ratio >= 0.5:
        return []
    return [
        _issue(
            QualityIssueType.PREFERENCE_UNDERREFLECTED,
            [item.get("slot", "UNKNOWN") for item in itinerary],
            f"사용자 선호 {len(preferences)}개 중 {len(matched)}개만 일정에 반영되었습니다.",
        )
    ]


def _evaluate_trip_purpose(state: TravelState) -> list[QualityIssue]:
    preferences = state.get("preference_profile", {}).get("keywords", [])
    if not preferences:
        return []
    primary_purpose = preferences[0]
    normalized_purposes = set(state.get("preference_profile", {}).get("soft", {}))
    itinerary = state.get("itinerary", [])
    if any(
        primary_purpose in item.get("tags", [])
        or bool(normalized_purposes & set(item.get("tags", [])))
        for item in itinerary
    ):
        return []
    return [
        _issue(
            QualityIssueType.TRIP_PURPOSE_UNCLEAR,
            [item.get("slot", "UNKNOWN") for item in itinerary],
            f"주요 여행 목적 '{primary_purpose}'이 일정에 드러나지 않습니다.",
        )
    ]


def _actions_for(
    issues: list[QualityIssue], itinerary: list[ItinerarySlot]
) -> list[ValidationAction]:
    by_slot = {item.get("slot"): item for item in itinerary}
    actions: dict[tuple[AgentName, tuple[str, ...]], ValidationAction] = {}
    itinerary_types = {
        QualityIssueType.SCHEDULE_TOO_TIGHT.value,
        QualityIssueType.ROUTE_INEFFICIENCY.value,
    }
    for issue in issues:
        slots = issue.get("slots", [])
        agent: AgentName = "itinerary"
        if issue.get("type") not in itinerary_types and slots:
            category = by_slot.get(slots[0], {}).get("category", "")
            agent = _CATEGORY_AGENT.get(category, "itinerary")
        key = (agent, tuple(slots))
        actions[key] = {
            "agent": agent,
            "slots": slots,
            "instruction": issue.get("reason", "일정 품질 문제를 해결합니다."),
        }
    return list(actions.values())


def evaluate_itinerary(state: TravelState) -> QualityValidationResult:
    itinerary = state.get("itinerary", [])
    issues = [
        *_evaluate_route(itinerary),
        *_evaluate_pacing(itinerary),
        *_evaluate_meals(itinerary),
        *_evaluate_repetition(itinerary),
        *_evaluate_preferences(state),
        *_evaluate_trip_purpose(state),
    ]
    deductions = sum(12 if issue.get("severity") == "MAJOR" else 6 for issue in issues)
    score = max(0, 100 - deductions)
    revise = score < 80 or any(issue.get("severity") == "MAJOR" for issue in issues)
    return {
        "status": "REVISE" if revise else "PASS",
        "score": score,
        "issues": issues,
        "next_actions": _actions_for(issues, itinerary) if revise else [],
    }


def validation_node(state: TravelState) -> TravelState:
    hard_result = state.get("hard_validation")
    if not hard_result or hard_result["status"] != "VALID":
        raise ValueError("Validation Agent는 Hard Validator를 통과한 일정만 평가할 수 있습니다.")
    result = evaluate_itinerary(state)
    return {
        "quality_validation": result,
        "retry_actions": result["next_actions"],
        "status": "completed" if result["status"] == "PASS" else "running",
        "messages": [
            f"일정 품질 평가 결과는 {result['status']}이며 점수는 {result['score']}점입니다."
        ],
    }
