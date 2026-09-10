from __future__ import annotations

from dataclasses import dataclass, field
from math import asin, cos, radians, sin, sqrt


@dataclass(frozen=True)
class OptimizerCandidate:
    place_id: str
    name: str
    category: str
    score: float
    subtype: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    opens_at: str | None = None
    closes_at: str | None = None
    source_ids: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    evidence_complete: bool = True
    address: str | None = None
    pet_allowed: bool | None = None
    max_pet_size: str | None = None
    indoor_pet_allowed: bool | None = None
    wheelchair_accessible: bool | None = None
    recommendation_reason: str = ""
    matched_conditions: tuple[str, ...] = ()


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
    subtype: str | None
    start_time: str
    end_time: str
    travel_minutes_from_previous: int
    latitude: float | None
    longitude: float | None
    source_ids: tuple[str, ...]
    tags: tuple[str, ...]
    address: str | None
    opens_at: str | None
    closes_at: str | None
    pet_allowed: bool | None
    max_pet_size: str | None
    indoor_pet_allowed: bool | None
    wheelchair_accessible: bool | None
    recommendation_reason: str
    matched_conditions: tuple[str, ...]


@dataclass(frozen=True)
class OptimizedPlan:
    visits: tuple[ScheduledVisit, ...]
    score: float


@dataclass
class _PartialPlan:
    visits: list[ScheduledVisit] = field(default_factory=list)
    used_non_lodging_place_ids: set[str] = field(default_factory=set)
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
    # 도심 단거리는 저속, 시군을 넘는 장거리는 간선도로 주행을 가정한다.
    # 외부 Directions API가 연결되기 전까지 쓰는 보수적 추정치다.
    average_speed_kmh = 30 if distance_km <= 10 else 50
    return max(5, round(distance_km / average_speed_kmh * 60))


def _candidate_score(
    candidate: OptimizerCandidate,
    travel_minutes: int,
    preferences: set[str],
) -> float:
    matched = set(candidate.tags) | set(candidate.matched_conditions)
    preference_matches = len(preferences & matched)
    # 검증 근거가 불완전한 고득점 후보가 완전한 후보를 밀어내면 이후 Hard Validator에서
    # 전체 일정이 폐기된다. 완전한 후보가 존재하는 동안은 선택되지 않도록 큰 패널티를 둔다.
    evidence_penalty = 10_000.0 if not candidate.evidence_complete else 0.0
    return candidate.score * 100 + preference_matches * 35 - travel_minutes * 2.0 - evidence_penalty


def _satisfies_required_policy(
    candidate: OptimizerCandidate,
    required_policy: dict[str, bool],
    required_policy_by_category: dict[str, dict[str, bool]],
) -> bool:
    category_policy = required_policy_by_category.get(candidate.category, {})
    for field, required in required_policy.items():
        if not required:
            continue
        if getattr(candidate, field) is not True:
            return False
    for field, required in category_policy.items():
        if not required:
            continue
        if getattr(candidate, field) is not True:
            return False
    return True


def optimize_itinerary(
    slots: list[SlotSpec],
    candidates_by_slot: dict[str, list[OptimizerCandidate]],
    preferences: list[str] | None = None,
    *,
    required_policy: dict[str, bool] | None = None,
    required_policy_by_category: dict[str, dict[str, bool]] | None = None,
    allow_lodging_repeats: bool = True,
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
    required_policy = required_policy or {}
    required_policy_by_category = required_policy_by_category or {}
    beam = [_PartialPlan()]
    for spec in slots:
        expanded: list[_PartialPlan] = []
        for partial in beam:
            previous = partial.visits[-1] if partial.visits else None
            for candidate in candidates_by_slot[spec.slot]:
                # 기본 숙소는 연박을 허용하되, 사용자가 여러 숙소를 원하면 숙소도 중복을 막는다.
                if (
                    (candidate.category != "LODGING" or not allow_lodging_repeats)
                    and candidate.place_id in partial.used_non_lodging_place_ids
                ):
                    continue
                if candidate.category != spec.category:
                    continue
                if not _satisfies_required_policy(
                    candidate,
                    required_policy,
                    required_policy_by_category,
                ):
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
                    subtype=candidate.subtype,
                    start_time=spec.start_time,
                    end_time=_clock(_minutes(spec.start_time) + spec.duration_minutes),
                    travel_minutes_from_previous=travel_minutes,
                    latitude=candidate.latitude,
                    longitude=candidate.longitude,
                    source_ids=candidate.source_ids,
                    tags=candidate.tags,
                    address=candidate.address,
                    opens_at=candidate.opens_at,
                    closes_at=candidate.closes_at,
                    pet_allowed=candidate.pet_allowed,
                    max_pet_size=candidate.max_pet_size,
                    indoor_pet_allowed=candidate.indoor_pet_allowed,
                    wheelchair_accessible=candidate.wheelchair_accessible,
                    recommendation_reason=candidate.recommendation_reason,
                    matched_conditions=candidate.matched_conditions,
                )
                expanded.append(
                    _PartialPlan(
                        visits=[*partial.visits, visit],
                        used_non_lodging_place_ids=(
                            partial.used_non_lodging_place_ids
                            if candidate.category == "LODGING" and allow_lodging_repeats
                            else {
                                *partial.used_non_lodging_place_ids,
                                candidate.place_id,
                            }
                        ),
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
