from __future__ import annotations

from dataclasses import asdict

from app.core.state import AgentName, RetryAction, ScheduledVisit, TravelState
from app.tools.itinerary_optimizer import (
    OptimizerCandidate,
    SlotSpec,
    optimize_itinerary,
)


_SLOT_RULES: dict[str, tuple[str, int]] = {
    "BREAKFAST": ("RESTAURANT", 60),
    "DESTINATION": ("DESTINATION", 120),
    "EXTRA_DESTINATION": ("DESTINATION", 120),
    "LUNCH": ("RESTAURANT", 60),
    "CAFE": ("RESTAURANT", 60),
    "DINNER": ("RESTAURANT", 90),
    "LODGING": ("LODGING", 60),
}

_CATEGORY_AGENT: dict[str, AgentName] = {
    "DESTINATION": "destination",
    "RESTAURANT": "restaurant",
    "LODGING": "lodging",
}

_DEFAULT_START_TIMES = ("10:00", "12:30", "15:00", "18:00")
_LUNCH_FIRST_START_TIMES = ("12:00", "14:00", "16:00", "18:00")
_DESTINATION_ONLY_START_TIMES = ("10:00", "15:00", "17:00", "19:00")
_CAFE_KEYWORDS = ("카페", "커피", "로스터", "베이커리", "디저트", "브런치")


def _slot_kind(slot: str) -> str:
    return slot.split("_", maxsplit=1)[1] if "_" in slot else slot


def _slot_day(slot: str) -> int:
    prefix = slot.split("_", maxsplit=1)[0]
    if not prefix.startswith("D") or not prefix[1:].isdigit():
        raise ValueError(f"지원하지 않는 슬롯 ID입니다: {slot}")
    return int(prefix[1:])


def _start_times_for_day(kinds: list[str]) -> tuple[str, ...]:
    if kinds and all(kind in {"DESTINATION", "EXTRA_DESTINATION"} for kind in kinds):
        return _DESTINATION_ONLY_START_TIMES
    if kinds and kinds[0] == "LUNCH":
        return _LUNCH_FIRST_START_TIMES
    return _DEFAULT_START_TIMES


def build_slot_specs(slots: list[str]) -> list[SlotSpec]:
    specs: list[SlotSpec] = []
    non_lodging_index_by_day: dict[int, int] = {}
    non_lodging_kinds_by_day: dict[int, list[str]] = {}
    for slot in slots:
        kind = _slot_kind(slot)
        if kind != "LODGING":
            non_lodging_kinds_by_day.setdefault(_slot_day(slot), []).append(kind)

    for slot in slots:
        kind = _slot_kind(slot)
        rule = _SLOT_RULES.get(kind)
        if rule is None:
            raise ValueError(f"지원하지 않는 슬롯 유형입니다: {kind}")
        category, duration = rule
        day = _slot_day(slot)
        if kind == "BREAKFAST":
            start_time = "08:00"
        elif kind == "LODGING":
            start_time = "20:00"
        else:
            index = non_lodging_index_by_day.get(day, 0)
            start_times = _start_times_for_day(non_lodging_kinds_by_day.get(day, []))
            start_time = start_times[min(index, len(start_times) - 1)]
            non_lodging_index_by_day[day] = index + 1
        specs.append(
            SlotSpec(
                slot=slot,
                day=day,
                category=category,
                start_time=start_time,
                duration_minutes=duration,
            )
        )
    return specs


def _restaurant_subtype(raw: dict[str, object]) -> str | None:
    explicit_subtype = raw.get("place_subtype") or raw.get("subtype")
    if explicit_subtype:
        return str(explicit_subtype)
    values: list[str] = [str(raw.get("name") or "")]
    values.extend(str(item) for item in raw.get("cuisine", []) or [])
    values.extend(str(item) for item in raw.get("matched_conditions", []) or [])
    joined = " ".join(values)
    if any(keyword in joined for keyword in _CAFE_KEYWORDS):
        return "CAFE"
    return None


def _is_cafe_candidate(candidate: OptimizerCandidate) -> bool:
    if candidate.subtype in {"CAFE", "BAKERY", "DESSERT"}:
        return True
    if candidate.subtype == "RESTAURANT":
        return False
    values = [candidate.name, candidate.subtype or "", *candidate.tags, *candidate.matched_conditions]
    joined = " ".join(values)
    return any(keyword in joined for keyword in _CAFE_KEYWORDS)


def _destination_candidates(state: TravelState) -> list[OptimizerCandidate]:
    candidates: list[OptimizerCandidate] = []
    for raw in state.get("destination_candidates", []):
        place_id = str(raw.get("destination_id", ""))
        candidates.append(
            OptimizerCandidate(
                place_id=f"D{place_id}",
                name=raw.get("title", "이름 없는 관광지"),
                category="DESTINATION",
                score=float(raw.get("score", 0.0)),
                latitude=raw.get("map_y"),
                longitude=raw.get("map_x"),
                source_ids=tuple(raw.get("source_ids", [])) or ((f"destination:{place_id}",) if place_id else ()),
                tags=tuple(
                    dict.fromkeys(
                        [
                            raw.get("theme_code", ""),
                            *raw.get("matched_conditions", []),
                            *raw.get("matched_keywords", []),
                        ]
                    )
                ),
                evidence_complete=bool(place_id and raw.get("source_types")),
                address=raw.get("addr1"),
                opens_at=raw.get("opens_at"),
                closes_at=raw.get("closes_at"),
                pet_allowed=raw.get("pet_allowed"),
                max_pet_size=raw.get("max_pet_size"),
                indoor_pet_allowed=raw.get("indoor_pet_allowed"),
                wheelchair_accessible=raw.get("wheelchair_accessible"),
                recommendation_reason=raw.get("reason", ""),
                matched_conditions=tuple(raw.get("matched_conditions", [])),
            )
        )
    return candidates


def _restaurant_candidates(state: TravelState) -> list[OptimizerCandidate]:
    candidates: list[OptimizerCandidate] = []
    for raw in state.get("restaurant_candidates", []):
        place_id = raw.get("place_id", "")
        candidates.append(
            OptimizerCandidate(
                place_id=place_id,
                name=raw.get("name", "이름 없는 음식점"),
                category="RESTAURANT",
                subtype=_restaurant_subtype(raw),
                score=float(raw.get("score", 0.0)),
                latitude=raw.get("latitude"),
                longitude=raw.get("longitude"),
                opens_at=raw.get("opens_at"),
                closes_at=raw.get("closes_at"),
                source_ids=tuple(raw.get("source_ids", [])) or ((f"restaurant:{place_id}",) if place_id else ()),
                tags=tuple(
                    dict.fromkeys(
                        [
                            *raw.get("cuisine", []),
                            *raw.get("matched_conditions", []),
                            *raw.get("matched_keywords", []),
                        ]
                    )
                ),
                evidence_complete=raw.get("status") == "OK",
                address=raw.get("address"),
                pet_allowed=raw.get("pet_allowed"),
                max_pet_size=raw.get("max_pet_size"),
                indoor_pet_allowed=raw.get("indoor_pet_allowed"),
                wheelchair_accessible=raw.get("wheelchair_accessible"),
                recommendation_reason=raw.get("reason", ""),
                matched_conditions=tuple(raw.get("matched_conditions", [])),
            )
        )
    return candidates


def _lodging_candidates(state: TravelState) -> list[OptimizerCandidate]:
    candidates: list[OptimizerCandidate] = []
    for index, raw in enumerate(state.get("lodging_candidates", [])):
        place_id = raw.get("place_id", "")
        distance = raw.get("distance_km")
        proximity_score = max(0.0, 1.0 - float(distance or 0.0) / 100)
        candidates.append(
            OptimizerCandidate(
                place_id=place_id,
                name=raw.get("name", "이름 없는 숙소"),
                category="LODGING",
                score=proximity_score - index * 0.001,
                latitude=raw.get("latitude"),
                longitude=raw.get("longitude"),
                opens_at=raw.get("opens_at"),
                closes_at=raw.get("closes_at"),
                source_ids=tuple(raw.get("source_ids", [])) or ((f"lodging:{place_id}",) if place_id else ()),
                tags=tuple(
                    dict.fromkeys(
                        ["LODGING", *raw.get("matched_conditions", []), *raw.get("matched_keywords", [])]
                    )
                ),
                evidence_complete=raw.get("status") == "OK",
                address=raw.get("address"),
                pet_allowed=raw.get("pet_allowed"),
                max_pet_size=raw.get("max_pet_size"),
                indoor_pet_allowed=raw.get("indoor_pet_allowed"),
                wheelchair_accessible=raw.get("wheelchair_accessible"),
                recommendation_reason=raw.get("reason", ""),
                matched_conditions=tuple(raw.get("matched_conditions", [])),
            )
        )
    return candidates


def collect_candidates_by_slot(
    state: TravelState, specs: list[SlotSpec]
) -> dict[str, list[OptimizerCandidate]]:
    by_category = {
        "DESTINATION": _destination_candidates(state),
        "RESTAURANT": _restaurant_candidates(state),
        "LODGING": _lodging_candidates(state),
    }
    result: dict[str, list[OptimizerCandidate]] = {}
    for spec in specs:
        candidates = list(by_category[spec.category])
        kind = _slot_kind(spec.slot)
        if kind == "CAFE":
            candidates = [candidate for candidate in candidates if _is_cafe_candidate(candidate)]
        elif kind in {"BREAKFAST", "LUNCH", "DINNER"}:
            candidates = [candidate for candidate in candidates if not _is_cafe_candidate(candidate)]
        result[spec.slot] = candidates
    return result


def _retry_actions(missing_slots: list[str]) -> list[RetryAction]:
    grouped: dict[AgentName, list[str]] = {}
    for slot in missing_slots:
        category = _SLOT_RULES[_slot_kind(slot)][0]
        grouped.setdefault(_CATEGORY_AGENT[category], []).append(slot)
    return [
        {
            "agent": agent,
            "slots": slots,
            "instruction": f"{', '.join(slots)} 슬롯에 사용할 후보를 다시 검색한다.",
        }
        for agent, slots in grouped.items()
    ]


def _serialize_visits(visits: tuple[object, ...]) -> list[ScheduledVisit]:
    serialized: list[ScheduledVisit] = []
    for visit in visits:
        data = asdict(visit)  # type: ignore[arg-type]
        data["source_ids"] = list(data["source_ids"])
        data["tags"] = list(data["tags"])
        data["matched_conditions"] = list(data["matched_conditions"])
        serialized.append(data)  # type: ignore[arg-type]
    return serialized


def itinerary_node(state: TravelState) -> TravelState:
    specs = build_slot_specs(state.get("slots", []))
    candidates_by_slot = collect_candidates_by_slot(state, specs)
    preferences = state.get("preference_profile", {}).get("keywords", [])
    request = state.get("request", {})
    lodging_slots = [spec for spec in specs if spec.category == "LODGING"]
    plans, missing_slots = optimize_itinerary(
        specs,
        candidates_by_slot,
        preferences,
        required_policy_by_category={
            "DESTINATION": {
                "pet_allowed": request.get("pet_allowed") is True,
                "indoor_pet_allowed": request.get("indoor_pet") is True,
                "wheelchair_accessible": request.get("wheelchair_accessible") is True,
            }
        },
        allow_lodging_repeats=len(lodging_slots) <= 1,
    )
    if not plans:
        return {
            "itinerary_status": "NEEDS_CANDIDATES",
            "status": "planned",
            "itinerary": [],
            "itinerary_alternatives": [],
            "missing_slots": missing_slots,
            "retry_actions": _retry_actions(missing_slots),
            "messages": [f"일정 후보가 부족한 슬롯 {len(missing_slots)}개를 발견했습니다."],
        }

    best, *alternatives = plans
    itinerary = _serialize_visits(best.visits)
    return {
        "itinerary_status": "READY",
        "status": "completed",
        "itinerary": itinerary,
        "itinerary_score": best.score,
        "itinerary_alternatives": [_serialize_visits(plan.visits) for plan in alternatives],
        "missing_slots": [],
        "retry_actions": [],
        "messages": [
            f"{len(itinerary)}개 슬롯으로 일정을 구성했습니다. "
            f"최적화 점수는 {best.score:.2f}점입니다."
        ],
    }
