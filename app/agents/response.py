from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from app.core.state import FinalTravelResponse, ItinerarySlot, ResponseDay, ResponseVisit, TravelState
from app.agents.response_llm import render_answer_with_llm


_POLICY_FIELDS = (
    "wheelchair_accessible",
    "pet_allowed",
    "indoor_pet_allowed",
    "max_pet_size",
)


def _pending_response(state: TravelState) -> FinalTravelResponse:
    itinerary_status = state.get("itinerary_status")
    hard_status = state.get("hard_validation", {}).get("status")
    quality_status = state.get("quality_validation", {}).get("status")
    failed = state.get("status") == "failed"
    violations = state.get("hard_validation", {}).get("violations", [])
    if failed and violations:
        reasons = list(
            dict.fromkeys(
                str(violation.get("reason", "")).strip()
                for violation in violations
                if violation.get("reason")
            )
        )
        summary = "요청 조건을 확인할 근거가 부족해 안전한 여행 일정을 확정하지 못했습니다."
        if reasons:
            summary += "\n" + "\n".join(f"- {reason}" for reason in reasons[:5])
    elif failed:
        summary = "여행 일정을 완성하지 못했습니다. 검색 및 검증 결과를 확인해 주세요."
    elif itinerary_status == "NEEDS_CANDIDATES":
        summary = "일정에 필요한 장소 후보를 추가로 검색하고 있습니다."
    elif hard_status == "INVALID":
        summary = "필수 조건을 충족하지 못해 일정을 수정하고 있습니다."
    elif quality_status == "REVISE":
        summary = "더 나은 동선과 일정 구성을 위해 일정을 수정하고 있습니다."
    else:
        summary = "최종 검증이 완료되지 않아 아직 여행 일정을 제공할 수 없습니다."
    return {
        "response_status": "FAILED" if failed else "PENDING",
        "title": "여행 일정 준비 중",
        "summary": summary,
        "answer": summary,
        "days": [],
        "notices": [],
        "quality_score": None,
        "source_ids": [],
    }


def _day(item: ItinerarySlot) -> int:
    slot = item.get("slot", "")
    prefix = slot.split("_", maxsplit=1)[0]
    if prefix.startswith("D") and prefix[1:].isdigit():
        return int(prefix[1:])
    try:
        return datetime.fromisoformat(item["start_at"]).date().toordinal()
    except (KeyError, ValueError):
        return 1


def _date(item: ItinerarySlot) -> str | None:
    try:
        return datetime.fromisoformat(item["start_at"]).date().isoformat()
    except (KeyError, ValueError):
        return None


def _time_range(item: ItinerarySlot) -> str:
    def clock(value: str | None) -> str:
        if not value:
            return "시간 미확인"
        try:
            return datetime.fromisoformat(value).strftime("%H:%M")
        except ValueError:
            return value

    return f"{clock(item.get('start_at'))}-{clock(item.get('end_at'))}"


def _recommendation_reason(item: ItinerarySlot, preferences: set[str]) -> str:
    matched = list(dict.fromkeys(item.get("matched_conditions", [])))
    preferred = [condition for condition in matched if condition in preferences]
    if preferred:
        return f"사용자가 선호한 {', '.join(preferred)} 조건과 일치합니다."
    if item.get("recommendation_reason"):
        return item["recommendation_reason"]
    return "검색 결과와 검증된 일정 구성을 바탕으로 선택했습니다."


def _visit(item: ItinerarySlot, preferences: set[str]) -> tuple[ResponseVisit, list[str]]:
    opens_at = item.get("opens_at")
    closes_at = item.get("closes_at")
    operating_hours = (
        f"{opens_at or '미확인'}-{closes_at or '미확인'}"
        if opens_at is not None or closes_at is not None
        else None
    )
    accessibility = {field: item.get(field) for field in _POLICY_FIELDS}
    unverified = [field for field, value in accessibility.items() if value is None]
    if operating_hours is None:
        unverified.append("operating_hours")
    if not item.get("address"):
        unverified.append("address")
    if not item.get("source_ids"):
        unverified.append("source_ids")

    name = item.get("name", item.get("place_id", "장소"))
    notices = [
        f"{name}: {field} 정보는 확인되지 않았습니다. 방문 전에 확인해 주세요."
        for field in unverified
    ]
    return (
        {
            "slot": item.get("slot", ""),
            "time": _time_range(item),
            "place_id": item.get("place_id", ""),
            "name": name,
            "category": item.get("category", ""),
            "address": item.get("address"),
            "recommendation_reason": _recommendation_reason(item, preferences),
            "operating_hours": operating_hours,
            "accessibility": accessibility,
            "travel_minutes_from_previous": item.get("travel_minutes_from_previous", 0),
            "unverified_fields": unverified,
            "source_ids": list(dict.fromkeys(item.get("source_ids", []))),
        },
        notices,
    )


def _answer(title: str, days: list[ResponseDay], notices: list[str]) -> str:
    lines = [title]
    for day in days:
        lines.append(f"\n{day['day']}일차 - {day['summary']}")
        for visit in day["visits"]:
            address = f" / {visit['address']}" if visit.get("address") else ""
            lines.append(
                f"- {visit['time']} {visit['name']}{address}: "
                f"{visit['recommendation_reason']}"
            )
    if notices:
        lines.append("\n방문 전 확인")
        lines.extend(f"- {notice}" for notice in notices)
    return "\n".join(lines)


def build_final_response(state: TravelState) -> FinalTravelResponse:
    if not (
        state.get("itinerary_status") == "READY"
        and state.get("hard_validation", {}).get("status") == "VALID"
        and state.get("quality_validation", {}).get("status") == "PASS"
    ):
        return _pending_response(state)

    preferences = set(state.get("preference_profile", {}).get("keywords", []))
    grouped: dict[int, list[tuple[ItinerarySlot, ResponseVisit]]] = defaultdict(list)
    notices: list[str] = []
    all_sources: list[str] = []
    itinerary = sorted(
        state.get("itinerary", []),
        key=lambda item: (_day(item), item.get("start_at", "")),
    )

    for raw_item in itinerary:
        item: ItinerarySlot = raw_item  # type: ignore[assignment]
        visit, visit_notices = _visit(item, preferences)
        grouped[_day(item)].append((item, visit))
        notices.extend(visit_notices)
        all_sources.extend(visit["source_ids"])

    days: list[ResponseDay] = []
    for day_number, entries in sorted(grouped.items()):
        visits = [visit for _, visit in entries]
        categories = list(dict.fromkeys(visit["category"] for visit in visits if visit["category"]))
        days.append(
            {
                "day": day_number,
                "date": _date(entries[0][0]),
                "summary": f"{', '.join(categories)} 중심의 {day_number}일차 코스",
                "visits": visits,
            }
        )

    region = state.get("request", {}).get("region") or "강원"
    title = f"{region} {len(days)}일 여행 일정"
    summary = f"검증을 통과한 {len(itinerary)}개 방문 일정입니다."
    unique_notices = list(dict.fromkeys(notices))
    source_ids = list(dict.fromkeys(all_sources))
    fallback_answer = _answer(title, days, unique_notices)
    return {
        "response_status": "READY",
        "title": title,
        "summary": summary,
        "answer": render_answer_with_llm(
            title=title,
            summary=summary,
            days=days,
            notices=unique_notices,
            quality_score=state.get("quality_validation", {}).get("score"),
            source_ids=source_ids,
            fallback_answer=fallback_answer,
        ),
        "days": days,
        "notices": unique_notices,
        "quality_score": state.get("quality_validation", {}).get("score"),
        "source_ids": source_ids,
    }


def response_node(state: TravelState) -> TravelState:
    return {"final_response": build_final_response(state)}
