from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from app.travel_profile.schema import AxisScores, TravelProfileRequest, TravelerType


AXIS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "C": ("도시", "도심", "시내", "카페", "시장", "박물관", "미술관", "city", "downtown", "museum"),
    "N": ("자연", "산", "바다", "해변", "숲", "계곡", "호수", "공원", "정원", "생태", "nature", "forest", "beach"),
    "A": ("체험", "액티비티", "등산", "트레킹", "서핑", "스키", "래프팅", "자전거", "캠핑", "모험", "activity", "hiking", "surfing"),
    "R": ("휴식", "힐링", "산책", "카페", "온천", "스파", "숙소", "명상", "여유", "rest", "healing", "spa"),
    "P": ("계획", "예약", "코스", "일정", "동선", "미리", "planned", "reservation", "itinerary"),
    "S": ("즉흥", "당일", "발길", "무계획", "우연", "spontaneous", "random", "today"),
    "F": ("유명", "대표", "명소", "랜드마크", "핫플", "필수", "popular", "famous", "landmark", "must-see"),
    "H": ("숨은", "로컬", "골목", "한적", "조용한", "비밀", "현지인", "hidden", "local", "quiet", "secret"),
}

AXES = (("space", "C", "N"), ("activity", "A", "R"), ("schedule", "P", "S"), ("place", "F", "H"))


@dataclass(frozen=True)
class Classification:
    traveler_type: TravelerType
    axis_scores: AxisScores
    raw_scores: dict[str, float]
    matched_counts: dict[str, int]
    total_weight: float
    consistency: float


def _recency(reference_time: datetime, activity_time: datetime) -> float:
    age_days = max(0.0, (reference_time - activity_time).total_seconds() / 86400)
    return max(0.25, math.pow(0.5, age_days / 90.0))


def _matches(text: str) -> set[str]:
    normalized = text.casefold()
    return {pole for pole, keywords in AXIS_KEYWORDS.items() if any(keyword.casefold() in normalized for keyword in keywords)}


def _percent_pair(left_score: float, right_score: float) -> tuple[int, int]:
    total = left_score + right_score
    if total <= 0:
        return 50, 50
    left = round(left_score / total * 100)
    return left, 100 - left


def classify(payload: TravelProfileRequest) -> Classification:
    scores = {pole: 0.0 for pole in AXIS_KEYWORDS}
    matched_counts = {pole: 0 for pole in AXIS_KEYWORDS}
    total_weight = 0.0

    def add(text: str, base_weight: float, occurred_at: datetime, behavior: str | None = None) -> None:
        nonlocal total_weight
        weight = base_weight * _recency(payload.reference_time, occurred_at)
        total_weight += weight
        matches = _matches(text)
        if behavior:
            matches.add(behavior)
        for pole in matches:
            scores[pole] += weight
            matched_counts[pole] += 1

    for item in payload.searches:
        add(" ".join(filter(None, (item.keyword, item.region))), 1.0, item.searched_at, "P")
    for item in payload.visits:
        add(" ".join(filter(None, (item.category, item.name, item.region))), 3.0, item.visited_at, "S")
    for course in payload.saved_courses:
        seen: set[str] = set()
        for place in course.places:
            key = place_identity(place.place_type, place.place_id, place.name)
            if key in seen:
                continue
            seen.add(key)
            add(" ".join(filter(None, (course.name, place.category, place.name, place.region))), 2.5, course.saved_at, "P")
    for item in payload.reviews:
        rating_factor = 1.0 if item.rating >= 4 else 0.5 if item.rating >= 3 else 0.2
        add(" ".join(filter(None, (item.name, item.place_type))), 3.0 * rating_factor, item.reviewed_at)

    normalized: dict[str, dict[str, int]] = {}
    code = ""
    margins: list[float] = []
    for axis, left, right in AXES:
        left_percent, right_percent = _percent_pair(scores[left], scores[right])
        normalized[axis] = {left: left_percent, right: right_percent}
        code += left if left_percent >= right_percent else right
        margins.append(abs(left_percent - right_percent) / 100)

    axis_scores = AxisScores.model_validate(normalized)
    return Classification(TravelerType(code), axis_scores, scores, matched_counts, total_weight, sum(margins) / len(margins))


def place_identity(place_type: object | None, place_id: int | None, name: str | None) -> str:
    place_type_value = getattr(place_type, "value", place_type) or ""
    if place_id is not None:
        return f"{str(place_type_value).casefold()}:{place_id}"
    return f"{str(place_type_value).casefold()}:{(name or '').strip().casefold()}"


def valid_signal_count(payload: TravelProfileRequest) -> int:
    saved_places = {place_identity(place.place_type, place.place_id, place.name) for course in payload.saved_courses for place in course.places}
    return len(payload.searches) + len(payload.visits) + len(saved_places) + len(payload.reviews)
