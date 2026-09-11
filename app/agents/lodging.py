from app.core.state import LodgingCandidate, TravelState
from app.search.be_client import search_client
from app.search.client import SearchClientError
from app.search.models import PlaceDomain, SearchRequest
from app.search.request_factory import build_search_diagnostic, build_search_relaxation, build_search_request

def lodging_node(state: TravelState) -> TravelState:
    search_request = _build_search_request(state)
    relaxation = build_search_relaxation(state, PlaceDomain.LODGING, "_LODGING")
    try:
        response = search_client.search(search_request)
    except SearchClientError as exc:
        return {"search_request": search_request, "lodging_candidates": [], "completed_agents": ["lodging"], "search_relaxations": [relaxation] if relaxation else [], "errors": [str(exc)], "messages": ["숙소 검색 서비스 호출에 실패했습니다."]}
    candidates: list[LodgingCandidate] = [{"place_id": item.place_id, "name": item.name, "distance_km": item.distance_km, "status": item.status.value, "missing_fields": item.missing_fields, "latitude": item.location.lat if item.location else None, "longitude": item.location.lon if item.location else None, "address": item.address or "", "reason": "검색 조건과 일치하는 숙소 후보입니다.", "matched_conditions": list(dict.fromkeys([*item.matched_preferences, *item.matched_keywords])), "matched_keywords": item.matched_keywords, "matched_preference_details": item.matched_preference_details, "region_code": item.region_code.value if item.region_code else None, "region_match": item.region_match, "opens_at": item.field_value("opens_at"), "closes_at": item.field_value("closes_at"), "pet_allowed": item.field_value("pet_allowed"), "max_pet_size": item.field_value("max_pet_size"), "indoor_pet_allowed": item.field_value("indoor_pet_allowed"), "wheelchair_accessible": item.field_value("wheelchair_accessible"), "source_ids": [f"lodging:{item.place_id}"]} for item in response.results]
    diagnostic = build_search_diagnostic(state, PlaceDomain.LODGING, "_LODGING", response.diagnostics)
    return {"search_request": search_request, "lodging_candidates": candidates, "completed_agents": ["lodging"], "search_relaxations": [relaxation] if relaxation else [], "search_diagnostics": [diagnostic] if diagnostic else [], "messages": [f"숙소 후보 {len(candidates)}개를 찾았습니다."]}

def _build_search_request(state: TravelState) -> SearchRequest:
    return build_search_request(state, PlaceDomain.LODGING, "_LODGING")
