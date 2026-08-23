from __future__ import annotations

from dataclasses import asdict

from app.core.state import AgentName, RetryAction, ScheduledVisit, TravelState
from app.tools.itinerary_optimizer import (
    OptimizerCandidate,
    SlotSpec,
    optimize_itinerary,
)


_SLOT_RULES: dict[str, tuple[str, str, int]] = {
    "BREAKFAST": ("RESTAURANT", "08:00", 60),
    "DESTINATION": ("DESTINATION", "10:00", 120),
    "LUNCH": ("RESTAURANT", "12:30", 60),
    "ACTIVITY": ("ACTIVITY", "14:30", 120),
    "DINNER": ("RESTAURANT", "18:00", 90),
    "LODGING": ("LODGING", "20:00", 60),
}

_CATEGORY_AGENT: dict[str, AgentName] = {
    "DESTINATION": "destination",
    "RESTAURANT": "restaurant",
    "LODGING": "lodging",
    "ACTIVITY": "activity",
}


def _slot_kind(slot: str) -> str:
    return slot.split("_", maxsplit=1)[1] if "_" in slot else slot


def _slot_day(slot: str) -> int:
    prefix = slot.split("_", maxsplit=1)[0]
    if not prefix.startswith("D") or not prefix[1:].isdigit():
        raise ValueError(f"지원하지 않는 슬롯 ID입니다: {slot}")
    return int(prefix[1:])


def build_slot_specs(slots: list[str]) -> list[SlotSpec]:
    specs: list[SlotSpec] = []
    for slot in slots:
        kind = _slot_kind(slot)
        rule = _SLOT_RULES.get(kind)
        if rule is None:
            raise ValueError(f"지원하지 않는 슬롯 유형입니다: {kind}")
        category, start_time, duration = rule
        specs.append(
            SlotSpec(
                slot=slot,
                day=_slot_day(slot),
                category=category,
                start_time=start_time,
                duration_minutes=duration,
            )
        )
    return specs


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
                source_ids=(f"destination:{place_id}",) if place_id else (),
                tags=(raw.get("theme_code", ""),),
                evidence_complete=bool(place_id and raw.get("source_types")),
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
                score=float(raw.get("score", 0.0)),
                latitude=raw.get("latitude"),
                longitude=raw.get("longitude"),
                opens_at=raw.get("opens_at"),
                closes_at=raw.get("closes_at"),
                source_ids=(f"restaurant:{place_id}",) if place_id else (),
                tags=tuple(raw.get("cuisine", [])),
                evidence_complete=raw.get("status") == "OK",
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
                source_ids=(f"lodging:{place_id}",) if place_id else (),
                tags=("LODGING",),
                evidence_complete=raw.get("status") == "OK",
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
        "ACTIVITY": [],
    }
    return {spec.slot: list(by_category[spec.category]) for spec in specs}


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
        serialized.append(data)  # type: ignore[arg-type]
    return serialized


def itinerary_node(state: TravelState) -> TravelState:
    specs = build_slot_specs(state.get("slots", []))
    candidates_by_slot = collect_candidates_by_slot(state, specs)
    preferences = state.get("preference_profile", {}).get("keywords", [])
    plans, missing_slots = optimize_itinerary(
        specs,
        candidates_by_slot,
        preferences,
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
