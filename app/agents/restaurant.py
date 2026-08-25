from app.core.state import RestaurantCandidate, TravelState
from app.search.be_client import search_client
from app.search.client import SearchClientError
from app.search.models import PlaceDomain, SearchRequest
from app.search.request_factory import build_search_request


def restaurant_node(state: TravelState) -> TravelState:
    search_request = _build_search_request(state)
    try:
        response = search_client.search(search_request)
    except SearchClientError as exc:
        return {"restaurant_search_request": search_request, "restaurant_candidates": [], "completed_agents": ["restaurant"], "errors": [str(exc)], "messages": ["음식점 검색 서비스 호출에 실패했습니다."]}

    candidates: list[RestaurantCandidate] = [
        {
            "place_id": item.place_id,
            "name": item.name,
            "distance_km": item.distance_km,
            "cuisine": [],
            "score": item.score,
            "status": item.status.value,
            "matched_conditions": item.matched_preferences,
            "missing_fields": item.missing_fields,
            "reason": "일부 정책 정보는 확인이 필요합니다." if item.missing_fields else "검색 조건에 맞는 음식점입니다.",
            "latitude": item.location.lat if item.location else None,
            "longitude": item.location.lon if item.location else None,
            "address": item.address or "",
            "opens_at": next((e.value for e in item.evidence if e.field == "opens_at"), None),
            "closes_at": next((e.value for e in item.evidence if e.field == "closes_at"), None),
            "pet_allowed": next((e.value for e in item.evidence if e.field == "pet_allowed"), None),
            "max_pet_size": next((e.value for e in item.evidence if e.field == "max_pet_size"), None),
            "indoor_pet_allowed": next((e.value for e in item.evidence if e.field == "indoor_pet_allowed"), None),
            "wheelchair_accessible": next((e.value for e in item.evidence if e.field == "wheelchair_accessible"), None),
            "source_ids": [f"restaurant:{item.place_id}"],
        }
        for item in response.results
    ]
    return {"restaurant_search_request": search_request, "restaurant_candidates": candidates, "completed_agents": ["restaurant"], "messages": [f"음식점 후보 {len(candidates)}개를 찾았습니다."]}


def _build_search_request(state: TravelState) -> SearchRequest:
    return build_search_request(state, PlaceDomain.RESTAURANT, "_LUNCH")
