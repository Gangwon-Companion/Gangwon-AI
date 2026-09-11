from __future__ import annotations

from datetime import datetime, time
from enum import StrEnum

from app.core.state import (
    AgentName,
    HardValidationResult,
    HardViolation,
    ItinerarySlot,
    TravelRequest,
    TravelState,
    ValidationAction,
)


class HardFailureCode(StrEnum):
    PET_NOT_ALLOWED = "PET_NOT_ALLOWED"
    PET_SIZE_NOT_ALLOWED = "PET_SIZE_NOT_ALLOWED"
    INDOOR_PET_NOT_ALLOWED = "INDOOR_PET_NOT_ALLOWED"
    WHEELCHAIR_INACCESSIBLE = "WHEELCHAIR_INACCESSIBLE"
    OUTSIDE_OPERATING_HOURS = "OUTSIDE_OPERATING_HOURS"
    TRAVEL_TIME_INFEASIBLE = "TRAVEL_TIME_INFEASIBLE"
    DUPLICATE_PLACE = "DUPLICATE_PLACE"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"


_PET_SIZE_ORDER = {"SMALL": 1, "MEDIUM": 2, "LARGE": 3}
_CATEGORY_AGENT: dict[str, AgentName] = {
    "DESTINATION": "destination",
    "RESTAURANT": "restaurant",
    "LODGING": "lodging",
}
_POLICY_VERIFIED_CATEGORIES = {"DESTINATION"}


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None


def _violation(
    code: HardFailureCode, item: ItinerarySlot, reason: str
) -> HardViolation:
    return {
        "code": code.value,
        "slots": [item.get("slot", "UNKNOWN")],
        "place_id": item.get("place_id", ""),
        "reason": reason,
        "source_ids": item.get("source_ids", []),
    }


def _has_policy_data(item: ItinerarySlot) -> bool:
    return item.get("category") in _POLICY_VERIFIED_CATEGORIES


def _required_evidence(request: TravelRequest, item: ItinerarySlot) -> list[str]:
    missing: list[str] = []
    if not item.get("place_id") or not item.get("source_ids"):
        missing.append("place source")
    if not item.get("opens_at") or not item.get("closes_at"):
        missing.append("operatingHours")
    if not _has_policy_data(item):
        return missing
    if request.get("pet_allowed") and item.get("pet_allowed") is None:
        missing.append("petAllowed")
    if request.get("indoor_pet") and item.get("indoor_pet_allowed") is None:
        missing.append("indoorPetAllowed")
    if request.get("wheelchair_accessible") and item.get("wheelchair_accessible") is None:
        missing.append("wheelchairAccessible")
    return missing


def _validate_item(request: TravelRequest, item: ItinerarySlot) -> list[HardViolation]:
    violations: list[HardViolation] = []
    missing = _required_evidence(request, item)
    if missing:
        violations.append(
            _violation(
                HardFailureCode.EVIDENCE_MISSING,
                item,
                f"필수 근거 데이터가 없습니다: {', '.join(missing)}",
            )
        )
        return violations

    if _has_policy_data(item):
        if request.get("pet_allowed") and item.get("pet_allowed") is False:
            violations.append(
                _violation(HardFailureCode.PET_NOT_ALLOWED, item, "반려동물 동반이 허용되지 않습니다.")
            )

        requested_size = request.get("pet_size")
        allowed_size = item.get("max_pet_size")
        if requested_size and allowed_size and (
            _PET_SIZE_ORDER.get(allowed_size, 0) < _PET_SIZE_ORDER.get(requested_size, 0)
        ):
            violations.append(
                _violation(
                    HardFailureCode.PET_SIZE_NOT_ALLOWED,
                    item,
                    f"{requested_size} 크기의 반려동물을 허용하지 않습니다.",
                )
            )

        if request.get("indoor_pet") and item.get("indoor_pet_allowed") is False:
            violations.append(
                _violation(
                    HardFailureCode.INDOOR_PET_NOT_ALLOWED,
                    item,
                    "필수 실내 반려동물 동반 조건을 만족하지 않습니다.",
                )
            )

        if request.get("wheelchair_accessible") and item.get("wheelchair_accessible") is False:
            violations.append(
                _violation(
                    HardFailureCode.WHEELCHAIR_INACCESSIBLE,
                    item,
                    "휠체어 접근 조건을 만족하지 않습니다.",
                )
            )

    start = _parse_datetime(item.get("start_at"))
    opens = _parse_time(item.get("opens_at"))
    closes = _parse_time(item.get("closes_at"))
    if start and opens and closes:
        visit_time = start.timetz().replace(tzinfo=None)
        in_hours = opens <= visit_time <= closes if opens <= closes else (
            visit_time >= opens or visit_time <= closes
        )
        if not in_hours:
            violations.append(
                _violation(
                    HardFailureCode.OUTSIDE_OPERATING_HOURS,
                    item,
                    "예정 방문 시각이 장소 운영시간 밖입니다.",
                )
            )
    return violations


def _agent_for(item: ItinerarySlot) -> AgentName:
    return _CATEGORY_AGENT.get(item.get("category", ""), "itinerary")


def _actions_for(
    violations: list[HardViolation], itinerary: list[ItinerarySlot]
) -> list[ValidationAction]:
    by_slot = {item.get("slot"): item for item in itinerary}
    actions: dict[tuple[AgentName, str], ValidationAction] = {}
    itinerary_codes = {
        HardFailureCode.TRAVEL_TIME_INFEASIBLE.value,
        HardFailureCode.DUPLICATE_PLACE.value,
    }
    for violation in violations:
        slot = violation.get("slots", ["UNKNOWN"])[0]
        agent: AgentName = "itinerary"
        if violation.get("code") not in itinerary_codes:
            agent = _agent_for(by_slot.get(slot, {}))
        key = (agent, slot)
        actions[key] = {
            "agent": agent,
            "slots": [slot],
            "instruction": violation.get("reason", "검증 실패 원인을 해결합니다."),
        }
    return list(actions.values())


def validate_itinerary(
    request: TravelRequest, itinerary: list[ItinerarySlot]
) -> HardValidationResult:
    violations: list[HardViolation] = []
    seen_non_lodging_places: dict[str, ItinerarySlot] = {}
    previous: ItinerarySlot | None = None

    for item in itinerary:
        violations.extend(_validate_item(request, item))
        place_id = item.get("place_id")
        category = item.get("category")
        first_visit = seen_non_lodging_places.get(place_id) if place_id else None
        if place_id and category != "LODGING" and first_visit:
            first_slot = first_visit.get("slot", "UNKNOWN")
            duplicate = _violation(
                HardFailureCode.DUPLICATE_PLACE,
                item,
                f"{first_slot} 슬롯과 동일한 장소가 중복되었습니다.",
            )
            duplicate["slots"] = [first_slot, item.get("slot", "UNKNOWN")]
            violations.append(duplicate)
        elif place_id and category != "LODGING":
            seen_non_lodging_places[place_id] = item

        if previous:
            previous_end = _parse_datetime(previous.get("end_at"))
            current_start = _parse_datetime(item.get("start_at"))
            travel_minutes = item.get("travel_minutes_from_previous")
            if previous_end and current_start and travel_minutes is not None:
                available_minutes = (current_start - previous_end).total_seconds() / 60
                if available_minutes < travel_minutes:
                    violation = _violation(
                        HardFailureCode.TRAVEL_TIME_INFEASIBLE,
                        item,
                        f"확보된 {available_minutes:.0f}분보다 이동시간 {travel_minutes}분이 깁니다.",
                    )
                    violation["slots"] = [
                        previous.get("slot", "UNKNOWN"),
                        item.get("slot", "UNKNOWN"),
                    ]
                    violations.append(violation)
        previous = item

    return {
        "status": "INVALID" if violations else "VALID",
        "violations": violations,
        "next_actions": _actions_for(violations, itinerary),
    }


def hard_validator_node(state: TravelState) -> TravelState:
    result = validate_itinerary(state["request"], state.get("itinerary", []))
    return {
        "hard_validation": result,
        "retry_actions": result["next_actions"],
        "messages": [
            "필수 조건 검증을 통과했습니다."
            if result["status"] == "VALID"
            else f"필수 조건 위반 {len(result['violations'])}건을 발견했습니다."
        ],
    }
