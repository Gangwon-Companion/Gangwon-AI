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
    candidates: list[LodgingCandidate] = [{"place_id": item.place_id, "name": item.name, "distance_km": item.distance_km, "status": item.status.value, "missing_fields": item.missing_fields, "latitude": item.location.lat if item.location else None, "longitude": item.location.lon if item.location else None, "address": item.address or "", "reason": "검색 조건과 일치하는 숙소 후보입니다.", "matched_conditions": item.matched_preferences, "opens_at": next((e.value for e in item.evidence if e.field == "opens_at"), None), "closes_at": next((e.value for e in item.evidence if e.field == "closes_at"), None), "pet_allowed": next((e.value for e in item.evidence if e.field == "pet_allowed"), None), "max_pet_size": next((e.value for e in item.evidence if e.field == "max_pet_size"), None), "indoor_pet_allowed": next((e.value for e in item.evidence if e.field == "indoor_pet_allowed"), None), "wheelchair_accessible": next((e.value for e in item.evidence if e.field == "wheelchair_accessible"), None), "source_ids": [f"lodging:{item.place_id}"]} for item in response.results]
    return {"search_request": search_request, "lodging_candidates": candidates, "completed_agents": ["lodging"], "messages": [f"숙소 후보 {len(candidates)}개를 찾았습니다."]}

def _build_search_request(state: TravelState) -> SearchRequest:
    return build_search_request(state, PlaceDomain.LODGING, "_LODGING")
