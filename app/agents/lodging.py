from app.core.state import LodgingCandidate, TravelState
from app.search.be_client import search_client
from app.search.client import SearchClientError
from app.search.models import PlaceDomain, SearchRequest
from app.search.request_factory import build_search_request

def lodging_node(state: TravelState) -> TravelState:
    search_request = _build_search_request(state)
    try:
        response = search_client.search(search_request)
    except SearchClientError as exc:
        return {"search_request": search_request, "lodging_candidates": [], "completed_agents": ["lodging"], "errors": [str(exc)], "messages": ["숙소 검색 서비스 호출에 실패했습니다."]}
    candidates: list[LodgingCandidate] = [{"place_id": item.place_id, "name": item.name, "distance_km": item.distance_km, "status": item.status.value, "missing_fields": item.missing_fields, "latitude": item.location.lat if item.location else None, "longitude": item.location.lon if item.location else None} for item in response.results]
    return {"search_request": search_request, "lodging_candidates": candidates, "completed_agents": ["lodging"], "messages": [f"숙소 후보 {len(candidates)}개를 찾았습니다."]}

def _build_search_request(state: TravelState) -> SearchRequest:
    return build_search_request(state, PlaceDomain.LODGING, "_LODGING")
