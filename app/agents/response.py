from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from app.core.state import (
    FinalTravelResponse,
    ItinerarySlot,
    ResponseDay,
    ResponseVisit,
    SearchRelaxation,
    TravelState,
)
from app.agents.response_llm import render_answer_with_llm


_POLICY_FIELDS = (
    "wheelchair_accessible",
    "pet_allowed",
    "indoor_pet_allowed",
    "max_pet_size",
)
_GENERAL_VISIT_NOTICE = (
    "운영시간과 이용 가능 여부는 달라질 수 있으니 방문 전 한 번 더 확인해 주세요."
)
_DOMAIN_LABELS = {
    "DESTINATION": "관광지",
    "RESTAURANT": "음식점",
    "LODGING": "숙소",
}


def _domain_label(value: object) -> str:
    return _DOMAIN_LABELS.get(str(value), "장소")


def _relaxation_notice(relaxation: SearchRelaxation) -> str:
    label = _domain_label(relaxation.get("domain"))
    original_query = str(relaxation.get("original_query") or "").strip()
    used_query = str(relaxation.get("used_query") or "").strip()
    original_regions = relaxation.get("original_regions", [])
    used_regions = relaxation.get("used_regions", [])
    regions_changed = bool(original_regions and used_regions and original_regions != used_regions)
    query_changed = bool(original_query and used_query and original_query != used_query)

    if query_changed and regions_changed:
        return (
            f"{label} 후보가 부족해 검색어를 '{original_query}'에서 '{used_query}'로 넓히고, "
            "인접 지역 후보까지 함께 검토했습니다."
        )
    if query_changed:
        return (
            f"{label} 후보가 부족해 검색어를 '{original_query}'에서 "
            f"'{used_query}'로 넓혀 다시 찾았습니다."
        )
    if regions_changed:
        return f"{label} 후보가 부족해 요청 지역 주변 후보까지 함께 검토했습니다."
    reason = str(relaxation.get("reason") or "").strip()
    return reason or f"{label} 후보가 부족해 검색 조건을 일부 완화했습니다."


def _relaxation_notices(state: TravelState) -> list[str]:
    notices = [
        _relaxation_notice(relaxation)
        for relaxation in state.get("search_relaxations", [])
    ]
    return list(dict.fromkeys(notices))


def _failure_reason_notices(state: TravelState) -> list[str]:
    notices: list[str] = []
    special_notice = _pet_accessible_destination_shortage_notice(state)
    if special_notice:
        notices.append(special_notice)

    missing_slots = state.get("missing_slots", [])
    if missing_slots:
        notices.append(f"일정에 필요한 장소 후보가 부족한 슬롯이 {len(missing_slots)}개 있습니다.")

    violations = (state.get("hard_validation") or {}).get("violations", [])
    for violation in violations[:5]:
        reason = str(violation.get("reason") or "").strip()
        if reason:
            notices.append(reason)

    issues = (state.get("quality_validation") or {}).get("issues", [])
    for issue in issues[:5]:
        reason = str(issue.get("reason") or "").strip()
        if reason:
            notices.append(reason)

    diagnostics = state.get("search_diagnostics", [])
    for diagnostic in diagnostics[-3:]:
        shortage = diagnostic.get("shortage", 0)
        if shortage and shortage > 0:
            notices.append(
                f"{_domain_label(diagnostic.get('domain'))} 검색 결과가 필요한 수보다 {shortage}개 부족했습니다."
            )
        unmatched_terms = diagnostic.get("unmatched_query_terms", [])
        if unmatched_terms:
            notices.append(
                f"{_domain_label(diagnostic.get('domain'))} 검색에서 {', '.join(unmatched_terms)} 조건과 직접 맞는 후보가 부족했습니다."
            )
        missing_evidence = diagnostic.get("missing_evidence_fields", [])
        if missing_evidence:
            notices.append(
                f"{_domain_label(diagnostic.get('domain'))} 후보에서 {', '.join(missing_evidence)} 정보를 충분히 확인하지 못했습니다."
            )

    if state.get("errors"):
        notices.append("일부 검색 또는 검증 과정에서 오류가 발생했습니다.")
    return list(dict.fromkeys(notices))


def _pet_accessible_destination_shortage_notice(state: TravelState) -> str | None:
    request = state.get("request", {})
    if not (request.get("pet_allowed") is True and request.get("wheelchair_accessible") is True):
        return None

    missing_slots = state.get("missing_slots", [])
    has_destination_shortage = any(str(slot).endswith("_DESTINATION") for slot in missing_slots)
    if not has_destination_shortage:
        return None

    return (
        "반려동물 동반과 휠체어 이용 조건을 모두 확인할 수 있는 관광지가 아직 충분하지 않아요. "
        "조건을 조금 넓히거나 방문지를 줄이면 더 여유로운 일정으로 다시 추천해드릴 수 있어요."
    )


def _failure_answer(summary: str, notices: list[str], relaxations: list[str]) -> str:
    lines = [summary]
    if relaxations:
        lines.append("\n시도한 보완")
        lines.extend(f"- {notice}" for notice in relaxations)
    if notices:
        lines.append("\n확인된 이유")
        lines.extend(f"- {notice}" for notice in notices)
    lines.append("\n다시 요청하실 때는 지역, 여행 기간, 꼭 필요한 조건을 조금 더 좁히거나 완화해 주세요.")
    return "\n".join(lines)


def _pending_response(state: TravelState) -> FinalTravelResponse:
    itinerary_status = state.get("itinerary_status")
    hard_validation = state.get("hard_validation") or {}
    quality_validation = state.get("quality_validation") or {}
    hard_status = hard_validation.get("status")
    quality_status = quality_validation.get("status")
    failed = state.get("status") == "failed"
    violations = hard_validation.get("violations", [])
    relaxation_notices = _relaxation_notices(state)
    failure_notices = _failure_reason_notices(state)
    if failed and violations:
        summary = "요청 조건을 확인할 근거가 부족해 안전한 여행 일정을 확정하지 못했습니다."
    elif failed:
        summary = "요청 조건에 맞는 장소 후보가 부족해 여행 일정을 완성하지 못했습니다."
    elif itinerary_status == "NEEDS_CANDIDATES":
        summary = "일정에 필요한 장소 후보를 추가로 검색하고 있습니다."
    elif hard_status == "INVALID":
        summary = "필수 조건을 충족하지 못해 일정을 수정하고 있습니다."
    elif quality_status == "REVISE":
        summary = "더 나은 동선과 일정 구성을 위해 일정을 수정하고 있습니다."
    else:
        summary = "최종 검증이 완료되지 않아 아직 여행 일정을 제공할 수 없습니다."
    answer = (
        _failure_answer(summary, failure_notices, relaxation_notices)
        if failed
        else summary
    )
    return {
        "response_status": "FAILED" if failed else "PENDING",
        "title": "여행 일정 준비 중",
        "summary": summary,
        "answer": answer,
        "days": [],
        "accommodations": [],
        "notices": [*relaxation_notices, *failure_notices],
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

    start = item.get("start_at") or item.get("start_time")
    end = item.get("end_at") or item.get("end_time")
    return f"{clock(start)}-{clock(end)}"


def _sort_time(item: ItinerarySlot) -> str:
    return item.get("start_at") or item.get("start_time") or ""


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
            "subtype": item.get("subtype"),
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


def _answer(
    title: str,
    days: list[ResponseDay],
    accommodations: list[ResponseVisit],
    relaxation_notices: list[str],
    notices: list[str],
) -> str:
    lines = [title]
    for day in days:
        lines.append(f"\n{day['day']}일차 - {day['summary']}")
        for visit in day["visits"]:
            address = f" / {visit['address']}" if visit.get("address") else ""
            lines.append(
                f"- {visit['time']} {visit['name']}{address}: "
                f"{visit['recommendation_reason']}"
            )
    if accommodations:
        lines.append("\n숙소")
        for lodging in accommodations:
            address = f" / {lodging['address']}" if lodging.get("address") else ""
            lines.append(
                f"- {lodging['time']} {lodging['name']}{address}: "
                f"{lodging['recommendation_reason']}"
            )
    if relaxation_notices:
        lines.append("\n시도한 보완")
        lines.extend(f"- {notice}" for notice in relaxation_notices)
    if notices:
        lines.append("\n방문 전 확인")
        lines.extend(f"- {notice}" for notice in notices)
    return "\n".join(lines)


def build_final_response(state: TravelState) -> FinalTravelResponse:
    hard_validation = state.get("hard_validation") or {}
    quality_validation = state.get("quality_validation") or {}
    if not (
        state.get("itinerary_status") == "READY"
        and hard_validation.get("status") == "VALID"
        and quality_validation.get("status") == "PASS"
    ):
        return _pending_response(state)

    preferences = set(state.get("preference_profile", {}).get("keywords", []))
    grouped: dict[int, list[tuple[ItinerarySlot, ResponseVisit]]] = defaultdict(list)
    accommodations: list[ResponseVisit] = []
    notices: list[str] = []
    all_sources: list[str] = []
    itinerary = sorted(
        state.get("itinerary", []),
        key=lambda item: (_day(item), _sort_time(item)),
    )

    for raw_item in itinerary:
        item: ItinerarySlot = raw_item  # type: ignore[assignment]
        visit, visit_notices = _visit(item, preferences)
        if item.get("category") == "LODGING":
            accommodations.append(visit)
        else:
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
    requested_days = state.get("request", {}).get("travel_days") or len(days)
    title = f"{region} {requested_days}일 여행 일정"
    summary = f"검증을 통과한 {sum(len(day['visits']) for day in days)}개 방문 일정입니다."
    if accommodations:
        summary += f" 숙소 {len(accommodations)}개는 별도로 안내합니다."
    relaxation_notices = _relaxation_notices(state)
    visit_notices = list(dict.fromkeys(notices))
    unique_notices = list(
        dict.fromkeys([_GENERAL_VISIT_NOTICE, *relaxation_notices, *visit_notices])
    )
    source_ids = list(dict.fromkeys(all_sources))
    fallback_answer = _answer(
        title,
        days,
        accommodations,
        relaxation_notices,
        [_GENERAL_VISIT_NOTICE, *visit_notices],
    )
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
            accommodations=accommodations,
        ),
        "days": days,
        "accommodations": accommodations,
        "notices": unique_notices,
        "quality_score": state.get("quality_validation", {}).get("score"),
        "source_ids": source_ids,
    }


def response_node(state: TravelState) -> TravelState:
    return {"final_response": build_final_response(state)}
