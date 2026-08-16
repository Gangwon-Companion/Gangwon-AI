from __future__ import annotations

from typing import TypedDict

from app.core.state import DestinationCandidate, TravelRequest, TravelState


class DestinationSearchRequest(TypedDict, total=False):
    region: str
    preferences: list[str]
    pet_allowed: bool
    wheelchair_accessible: bool
    limit: int


def destination_node(state: TravelState) -> TravelState:
    request = state["request"]

    search_request = _build_destination_search_request(request)
    candidates = _search_destinations(search_request)

    if not candidates:
        return {
            "destination_candidates": [],
            "messages": ["조건에 맞는 관광지 후보를 찾지 못했습니다."]
        }

    return {
        "destination_candidates": candidates,
        "messages": [f"관광지 후보 {len(candidates)}개를 찾았습니다."]
    }


def _build_destination_search_request(request: TravelRequest) -> DestinationSearchRequest:
    # 공통 Search Tool이 받을 수 있도록 사용자 요청에서 목적지 검색 조건만 추린다.
    return {
        "region": request.get("region", ""),
        "preferences": request.get("preferences", []),
        "pet_allowed": request.get("pet_allowed", False),
        "wheelchair_accessible": request.get("wheelchair_accessible", False),
        "limit": 5
    }


def _search_destinations(search_request: DestinationSearchRequest) -> list[DestinationCandidate]:
    # TODO: 공통 Search Tool이 구현되면 이 Mock 검색을 실제 검색 호출로 교체한다.
    region = search_request.get("region", "강원")
    preferences = search_request.get("preferences", [])
    matched_conditions = ["region"]
    if preferences:
        matched_conditions.append("preferences")
    if search_request.get("pet_allowed"):
        matched_conditions.append("pet_allowed")
    if search_request.get("wheelchair_accessible"):
        matched_conditions.append("wheelchair_accessible")

    mock_candidates: list[DestinationCandidate] = [
        {
            "destination_id": 1,
            "title": "경포해변",
            "addr1": f"{region} 경포로 일대",
            "map_x": 128.9076,
            "map_y": 37.8058,
            "theme_code": "NA",
            "source_types": ["KOREAN"],
            "score": 0.92,
            "reason": "바다와 자연 선호에 잘 맞는 대표 관광지 후보입니다.",
            "matched_conditions": matched_conditions,
        },
        {
            "destination_id": 2,
            "title": "오죽헌",
            "addr1": f"{region} 율곡로 일대",
            "map_x": 128.8786,
            "map_y": 37.7794,
            "theme_code": "HS",
            "source_types": ["KOREAN", "ACCESSIBILITY"],
            "score": 0.86,
            "reason": "역사 테마와 실내외 관람 동선을 함께 고려할 수 있는 후보입니다.",
            "matched_conditions": matched_conditions,
        },
    ]
    return mock_candidates[: search_request.get("limit", 5)]
