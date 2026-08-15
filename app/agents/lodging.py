from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

from app.core.state import LodgingCandidate, TravelState


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
    if request.get("max_price") is not None:
        filters["maxPrice"] = request["max_price"]

    return SearchRequest(
        type="LODGING",
        query=str(request.get("message") or "숙소").strip(),
        region=request.get("region"),
        filters=filters,
    )

_PET_SIZE_ORDER = {"SMALL": 1, "MEDIUM": 2, "LARGE": 3}

_REGION_CENTERS: dict[str, tuple[float, float]] = {
    "강릉": (37.75, 128.90),
}

# Elasticsearch 기반 공용 Search Tool(plan.md 6장)이 준비되기 전까지 쓰는 임시 데이터다.
_MOCK_LODGINGS: list[dict[str, object]] = [
    {
        "place_id": "L101",
        "name": "강릉 오션뷰 펫프렌들리 호텔",
        "lat": 37.7715,
        "lon": 128.9470,
        "pet_size_policy": "SMALL",
        "wheelchair_accessible_room": True,
        "nights_available": True,
    },
    {
        "place_id": "L102",
        "name": "강릉 한옥 스테이",
        "lat": 37.7519,
        "lon": 128.8761,
        "pet_size_policy": None,
        "wheelchair_accessible_room": None,
        "nights_available": True,
    },
    {
        "place_id": "L103",
        "name": "강릉 시내 비즈니스 호텔",
        "lat": 37.7519,
        "lon": 128.8969,
        "pet_size_policy": "MEDIUM",
        "wheelchair_accessible_room": True,
        "nights_available": True,
    },
]


def _search_lodging(region: str) -> list[dict[str, object]]:
    return _MOCK_LODGINGS if region in _REGION_CENTERS else []


def _distance_km(region: str, lat: float, lon: float) -> float | None:
    center = _REGION_CENTERS.get(region)
    if center is None:
        return None
    lat1, lon1, lat2, lon2 = map(radians, (center[0], center[1], lat, lon))
    d_lat, d_lon = lat2 - lat1, lon2 - lon1
    a = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    return round(2 * 6371 * asin(sqrt(a)), 2)


# 필수조건을 만족하는지 확인한다. 정책 정보가 없으면 위반이 아니라 근거 부족으로 취급한다.
def _verify_policy(
    candidate: dict[str, object], pet_allowed: bool, pet_size: str | None, wheelchair_accessible: bool
) -> tuple[bool, list[str]]:
    missing: list[str] = []

    pet_size_policy = candidate.get("pet_size_policy")
    if pet_allowed and pet_size:
        if pet_size_policy is None:
            missing.append("pet_size_policy")
        elif _PET_SIZE_ORDER.get(pet_size_policy, 0) < _PET_SIZE_ORDER.get(pet_size, 0):
            return False, missing

    wheelchair_room = candidate.get("wheelchair_accessible_room")
    if wheelchair_accessible:
        if wheelchair_room is None:
            missing.append("wheelchair_accessible_room")
        elif wheelchair_room is False:
            return False, missing

    return True, missing


# 반려동물 정책, 무장애 객실, 연박 가능 여부를 확인하고 후보를 거리순으로 반환한다.
def lodging_node(state: TravelState) -> TravelState:
    request = state["request"]
    search_request = _build_search_request(state)
    region = request.get("region", "")
    pet_allowed = bool(request.get("pet_allowed"))
    pet_size = request.get("pet_size")
    wheelchair_accessible = bool(request.get("wheelchair_accessible"))

    candidates: list[LodgingCandidate] = []
    for raw in _search_lodging(region):
        passes, missing_fields = _verify_policy(raw, pet_allowed, pet_size, wheelchair_accessible)
        if not passes:
            continue
        if not raw.get("nights_available", True):
            continue

        candidates.append(
            {
                "place_id": raw["place_id"],
                "name": raw["name"],
                "distance_km": _distance_km(region, raw["lat"], raw["lon"]),
                "status": "INSUFFICIENT_EVIDENCE" if missing_fields else "OK",
                "missing_fields": missing_fields,
            }
        )

    candidates.sort(key=lambda c: (c["distance_km"] is None, c["distance_km"] or 0.0))

    messages = [
        f"{region or '미지정 지역'}에서 숙소 후보 {len(candidates)}개를 찾았습니다."
        if candidates
        else f"{region or '미지정 지역'}에서 조건에 맞는 숙소 후보를 찾지 못했습니다."
    ]

    # status는 쓰지 않는다. 병렬 Agent가 각자 쓰면 reducer가 없어 마지막 병합 값이 이기고,
    # 다른 Agent가 아직 끝나지 않았는데 completed가 나갈 수 있다(plan.md 1.5).
    return {
        "search_request": search_request,
        "lodging_candidates": candidates,
        "messages": messages,
    }
