from __future__ import annotations

from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt


@dataclass(frozen=True)
class OptimizerCandidate:
    place_id: str
    name: str
    category: str
    score: float
    latitude: float | None = None
    longitude: float | None = None
    opens_at: str | None = None
    closes_at: str | None = None
    source_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    evidence_complete: bool = True


@dataclass(frozen=True)
class SlotSpec:
    slot: str
    day: int
    category: str
    start_time: str
    duration_minutes: int


@dataclass(frozen=True)
class ScheduledVisit:
    slot: str
    day: int
    place_id: str
    name: str
    category: str
    start_time: str
    end_time: str
    travel_minutes_from_previous: int
    latitude: float | None
    longitude: float | None
    source_ids: tuple[str, ...]
    tags: tuple[str, ...]


@dataclass(frozen=True)
class OptimizedPlan:
    visits: tuple[ScheduledVisit, ...]
    score: float


@dataclass
class _PartialPlan:
    visits: list[ScheduledVisit] = field(default_factory=list)
    used_place_ids: set[str] = field(default_factory=set)
    score: float = 0.0


def _minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def _clock(total_minutes: int) -> str:
    total_minutes %= 24 * 60
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def is_open_at(candidate: OptimizerCandidate, visit_time: str) -> bool:
    if candidate.opens_at is None or candidate.closes_at is None:
        return True
    visit = _minutes(visit_time)
    opens = _minutes(candidate.opens_at)
    closes = _minutes(candidate.closes_at)
    if opens <= closes:
        return opens <= visit <= closes
    return visit >= opens or visit <= closes


def estimate_travel_minutes(
    previous: ScheduledVisit | None, candidate: OptimizerCandidate
) -> int:
    if previous is None:
        return 0
    coords = (
        previous.latitude,
        previous.longitude,
        candidate.latitude,
        candidate.longitude,
    )
    if any(value is None for value in coords):
        return 15
    lat1, lon1, lat2, lon2 = (radians(float(value)) for value in coords)
    d_lat, d_lon = lat2 - lat1, lon2 - lon1
    a = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    distance_km = 2 * 6371 * asin(sqrt(a))
    return max(5, round(distance_km / 30 * 60))


def _candidate_score(
    candidate: OptimizerCandidate,
    travel_minutes: int,
    preferences: set[str],
) -> float:
    preference_matches = len(preferences & set(candidate.tags))
    evidence_penalty = 15.0 if not candidate.evidence_complete else 0.0
    return candidate.score * 100 + preference_matches * 5 - travel_minutes * 0.15 - evidence_penalty


def optimize_itinerary(
    slots: list[SlotSpec],
    candidates_by_slot: dict[str, list[OptimizerCandidate]],
    preferences: list[str] | None = None,
    *,
    beam_width: int = 20,
    top_k: int = 3,
) -> tuple[list[OptimizedPlan], list[str]]:
    """중복과 운영시간 제약을 적용해 점수가 높은 일정 조합을 반환한다."""
    if beam_width < 1 or top_k < 1:
        raise ValueError("beam_width와 top_k는 1 이상이어야 합니다.")

    missing_slots = [spec.slot for spec in slots if not candidates_by_slot.get(spec.slot)]
    if missing_slots:
        return [], missing_slots

    preference_set = set(preferences or [])
    beam = [_PartialPlan()]
    for spec in slots:
        expanded: list[_PartialPlan] = []
        for partial in beam:
            previous = partial.visits[-1] if partial.visits else None
            for candidate in candidates_by_slot[spec.slot]:
                # 연박은 같은 숙소를 유지하는 편이 자연스럽다. 숙소 외 장소만 중복을 막는다.
                if (
                    candidate.place_id in partial.used_place_ids
                    and candidate.category != "LODGING"
                ):
                    continue
                if candidate.category != spec.category:
                    continue
                if not is_open_at(candidate, spec.start_time):
                    continue
                travel_minutes = estimate_travel_minutes(previous, candidate)
                visit = ScheduledVisit(
                    slot=spec.slot,
                    day=spec.day,
                    place_id=candidate.place_id,
                    name=candidate.name,
                    category=candidate.category,
                    start_time=spec.start_time,
                    end_time=_clock(_minutes(spec.start_time) + spec.duration_minutes),
                    travel_minutes_from_previous=travel_minutes,
                    latitude=candidate.latitude,
                    longitude=candidate.longitude,
                    source_ids=candidate.source_ids,
                    tags=candidate.tags,
                )
                expanded.append(
                    _PartialPlan(
                        visits=[*partial.visits, visit],
                        used_place_ids={*partial.used_place_ids, candidate.place_id},
                        score=partial.score
                        + _candidate_score(candidate, travel_minutes, preference_set),
                    )
                )
        if not expanded:
            return [], [spec.slot]
        expanded.sort(key=lambda plan: plan.score, reverse=True)
        beam = expanded[:beam_width]

    plans = [
        OptimizedPlan(visits=tuple(plan.visits), score=round(plan.score, 2))
        for plan in beam[:top_k]
    ]
    return plans, []
