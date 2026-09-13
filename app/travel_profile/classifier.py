from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from app.travel_profile.schema import TravelProfileRequest, TravelerType


TYPE_KEYWORDS: dict[TravelerType, tuple[str, ...]] = {
    TravelerType.NATURE_HEALING: (
        "nature", "자연", "산", "바다", "해변", "숲", "호수", "계곡", "공원", "정원",
        "산책", "힐링", "휴식", "한적", "경관", "생태",
    ),
    TravelerType.PET_COMPANION: (
        "pet", "반려", "강아지", "고양이", "애견", "동반", "댕댕이",
    ),
    TravelerType.LOCAL_FOOD_EXPLORER: (
        "food", "restaurant", "음식", "맛집", "식당", "카페", "시장", "먹거리",
        "향토", "로컬푸드", "디저트", "커피",
    ),
    TravelerType.ACTIVITY_ADVENTURE: (
        "activity", "레저", "액티비티", "등산", "트레킹", "서핑", "스키", "래프팅",
        "자전거", "패러글라이딩", "캠핑", "모험", "체험",
    ),
    TravelerType.CULTURE_EXPLORER: (
        "culture", "문화", "역사", "박물관", "미술관", "전시", "유적", "사찰",
        "축제", "공연", "전통", "문화재",
    ),
}


@dataclass(frozen=True)
class Classification:
    traveler_type: TravelerType
    scores: dict[TravelerType, float]
    matched_counts: dict[TravelerType, int]
    total_weight: float
    top_share: float
    consistency: float


def _recency(reference_time: datetime, activity_time: datetime) -> float:
    age_days = max(0.0, (reference_time - activity_time).total_seconds() / 86400)
    return max(0.25, math.pow(0.5, age_days / 90.0))


def _matched_types(text: str) -> set[TravelerType]:
    normalized = text.casefold()
    return {
        traveler_type
        for traveler_type, keywords in TYPE_KEYWORDS.items()
        if any(keyword.casefold() in normalized for keyword in keywords)
    }


def classify(payload: TravelProfileRequest) -> Classification:
    scores = {traveler_type: 0.0 for traveler_type in TYPE_KEYWORDS}
    matched_counts: Counter[TravelerType] = Counter()
    total_weight = 0.0

    def add(text: str, base_weight: float, occurred_at: datetime) -> None:
        nonlocal total_weight
        weight = base_weight * _recency(payload.reference_time, occurred_at)
        total_weight += weight
        matches = _matched_types(text)
        if not matches:
            return
        divided = weight / len(matches)
        for matched in matches:
            scores[matched] += divided
            matched_counts[matched] += 1

    for item in payload.searches:
        add(" ".join(filter(None, (item.keyword, item.region))), 1.0, item.searched_at)
    for item in payload.visits:
        add(" ".join(filter(None, (item.category, item.name, item.region))), 3.0, item.visited_at)
    for course in payload.saved_courses:
        seen: set[str] = set()
        for place in course.places:
            key = place_identity(place.place_type, place.place_id, place.name)
            if key in seen:
                continue
            seen.add(key)
            add(" ".join(filter(None, (course.name, place.category, place.name, place.region))), 2.5, course.saved_at)
    for item in payload.reviews:
        # High ratings express preference more strongly; low ratings remain weak activity signals.
        rating_factor = 1.0 if item.rating >= 4 else 0.5 if item.rating >= 3 else 0.2
        add(" ".join(filter(None, (item.name, item.place_type))), 3.0 * rating_factor, item.reviewed_at)

    ranked = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0].value))
    top_type, top_score = ranked[0]
    second_score = ranked[1][1]
    classified_weight = sum(scores.values())
    top_share = top_score / classified_weight if classified_weight else 0.0
    consistency = top_score / max(top_score + second_score, 0.0001) if top_score else 0.0

    if top_score == 0 or (second_score > 0 and second_score / top_score >= 0.85):
        result_type = TravelerType.BALANCED_TRAVELER
    else:
        result_type = top_type
    return Classification(result_type, scores, dict(matched_counts), total_weight, top_share, consistency)


def place_identity(place_type: object | None, place_id: int | None, name: str | None) -> str:
    place_type_value = getattr(place_type, "value", place_type) or ""
    if place_id is not None:
        return f"{str(place_type_value).casefold()}:{place_id}"
    return f"{str(place_type_value).casefold()}:{(name or '').strip().casefold()}"


def valid_signal_count(payload: TravelProfileRequest) -> int:
    saved_places: set[str] = set()
    for course in payload.saved_courses:
        for place in course.places:
            saved_places.add(place_identity(place.place_type, place.place_id, place.name))
    return len(payload.searches) + len(payload.visits) + len(saved_places) + len(payload.reviews)
