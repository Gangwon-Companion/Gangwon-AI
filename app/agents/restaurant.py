from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from app.core.state import RestaurantCandidate, TravelState


@dataclass(frozen=True)
class SearchRequest:
    type: str
    query: str
    region: str | None
    filters: dict[str, object]


def _build_search_request(state: TravelState) -> SearchRequest:
    request = state["request"]
    filters: dict[str, object] = {}

    if request.get("pet_size"):
        filters["petSize"] = request["pet_size"]
    if request.get("wheelchair_accessible"):
        filters["wheelchair"] = True
    if request.get("indoor_pet"):
        filters["indoorPet"] = True
    if request.get("max_price") is not None:
        filters["maxPricePerPerson"] = request["max_price"]

    return SearchRequest(
        type="RESTAURANT",
        query=str(request.get("message") or "음식점").strip(),
        region=request.get("region"),
        filters=filters,
    )


_PET_SIZE_ORDER = {"SMALL": 1, "MEDIUM": 2, "LARGE": 3}

_REGION_CENTERS: dict[str, tuple[float, float]] = {
    "강릉": (37.75, 128.90),
}

# 공용 Search Tool이 연결되기 전까지 Agent의 입출력을 검증하기 위한 임시 데이터다.
_MOCK_RESTAURANTS: list[dict[str, object]] = [
    {
        "place_id": "R101",
        "name": "강릉 솔향 한식당",
        "region": "강릉",
        "lat": 37.7540,
        "lon": 128.8990,
        "cuisine": ["KOREAN"],
        "pet_size_policy": "LARGE",
        "indoor_pet": True,
        "wheelchair_accessible": True,
        "open_now": True,
        "base_score": 0.90,
    },
    {
        "place_id": "R102",
        "name": "경포 바다 밥상",
        "region": "강릉",
        "lat": 37.7950,
        "lon": 128.9080,
        "cuisine": ["KOREAN", "SEAFOOD"],
        "pet_size_policy": "SMALL",
        "indoor_pet": False,
        "wheelchair_accessible": True,
        "open_now": True,
        "base_score": 0.86,
    },
    {
        "place_id": "R103",
        "name": "초당 정원 식당",
        "region": "강릉",
        "lat": 37.7900,
        "lon": 128.9140,
        "cuisine": ["KOREAN"],
        "pet_size_policy": None,
        "indoor_pet": None,
        "wheelchair_accessible": None,
        "open_now": True,
        "base_score": 0.82,
    },
]


def _search_restaurant(region: str) -> list[dict[str, object]]:
    return [item for item in _MOCK_RESTAURANTS if item["region"] == region]


def _distance_km(region: str, lat: float, lon: float) -> float | None:
    center = _REGION_CENTERS.get(region)
    if center is None:
        return None
    lat1, lon1, lat2, lon2 = map(radians, (center[0], center[1], lat, lon))
    d_lat, d_lon = lat2 - lat1, lon2 - lon1
    a = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    return round(2 * 6371 * asin(sqrt(a)), 2)


def _verify_policy(
    candidate: dict[str, object],
    pet_size: str | None,
    wheelchair: bool,
    indoor_pet: bool,
) -> tuple[bool, list[str], list[str]]:
    missing: list[str] = []
    matched: list[str] = []

    if pet_size:
        policy = candidate.get("pet_size_policy")
        if policy is None:
            missing.append("petSize")
        elif _PET_SIZE_ORDER.get(str(policy), 0) < _PET_SIZE_ORDER.get(pet_size, 0):
            return False, missing, matched
        else:
            matched.append("petSize")

    for requested, source_field, response_field in (
        (wheelchair, "wheelchair_accessible", "wheelchair"),
        (indoor_pet, "indoor_pet", "indoorPet"),
    ):
        if not requested:
            continue
        value = candidate.get(source_field)
        if value is None:
            missing.append(response_field)
        elif value is False:
            return False, missing, matched
        else:
            matched.append(response_field)

    return True, missing, matched


def restaurant_node(state: TravelState) -> TravelState:
    request = state["request"]
    region = str(request.get("region") or "")
    search_request = _build_search_request(state)
    candidates: list[RestaurantCandidate] = []

    for raw in _search_restaurant(region):
        if not raw.get("open_now", True):
            continue
        passes, missing_fields, matched_conditions = _verify_policy(
            raw,
            request.get("pet_size"),
            bool(request.get("wheelchair_accessible")),
            bool(request.get("indoor_pet")),
        )
        if not passes:
            continue

        distance = _distance_km(region, float(raw["lat"]), float(raw["lon"]))
        score = max(0.0, float(raw["base_score"]) - (distance or 0.0) * 0.01)
        if missing_fields:
            score *= 0.7

        candidates.append(
            {
                "place_id": str(raw["place_id"]),
                "name": str(raw["name"]),
                "distance_km": distance,
                "cuisine": list(raw["cuisine"]),
                "score": round(score, 3),
                "status": "INSUFFICIENT_EVIDENCE" if missing_fields else "OK",
                "matched_conditions": matched_conditions,
                "missing_fields": missing_fields,
                "reason": (
                    "일부 필수 정책 정보는 추가 확인이 필요합니다."
                    if missing_fields
                    else "요청한 필수 조건이 확인된 음식점입니다."
                ),
            }
        )

    candidates.sort(key=lambda item: (item["status"] != "OK", -item["score"]))
    message = (
        f"{region or '미지정 지역'}에서 음식점 후보 {len(candidates)}개를 찾았습니다."
        if candidates
        else f"{region or '미지정 지역'}에서 조건에 맞는 음식점 후보를 찾지 못했습니다."
    )
    return {
        "restaurant_search_request": search_request,
        "restaurant_candidates": candidates,
        "messages": [message],
    }
