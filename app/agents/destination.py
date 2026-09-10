from app.core.state import DestinationCandidate, TravelState
from app.search.be_client import search_client
from app.search.client import SearchClientError
from app.search.models import PlaceDomain, SearchRequest
from app.search.request_factory import build_search_diagnostic, build_search_relaxation, build_search_request

def destination_node(state: TravelState) -> TravelState:
    search_request = _build_search_request(state)
    relaxation = build_search_relaxation(state, PlaceDomain.DESTINATION, "_DESTINATION")
    try:
        response = search_client.search(search_request)
    except SearchClientError as exc:
        return {"destination_search_request": search_request, "destination_candidates": [], "completed_agents": ["destination"], "search_relaxations": [relaxation] if relaxation else [], "errors": [str(exc)], "messages": ["관광지 검색 서비스 호출에 실패했습니다."]}
    candidates: list[DestinationCandidate] = []
    for item in response.results:
        destination_id = int(item.place_id.split(":", 1)[1])
        candidates.append({"destination_id": destination_id, "title": item.name, "addr1": item.address or "", "map_x": item.location.lon if item.location else 0.0, "map_y": item.location.lat if item.location else 0.0, "theme_code": "", "source_types": sorted({e.source for e in item.evidence}), "score": item.score, "reason": "검색어와 선호조건을 기준으로 선정한 관광지 후보입니다.", "matched_conditions": list(dict.fromkeys([*item.matched_preferences, *item.matched_keywords])), "matched_keywords": item.matched_keywords, "matched_preference_details": item.matched_preference_details, "region_code": item.region_code.value if item.region_code else None, "region_match": item.region_match, "opens_at": item.field_value("opens_at"), "closes_at": item.field_value("closes_at"), "pet_allowed": item.field_value("pet_allowed"), "max_pet_size": item.field_value("max_pet_size"), "indoor_pet_allowed": item.field_value("indoor_pet_allowed"), "wheelchair_accessible": item.field_value("wheelchair_accessible"), "source_ids": [f"destination:{destination_id}"]})
    diagnostic = build_search_diagnostic(state, PlaceDomain.DESTINATION, "_DESTINATION", response.diagnostics)
    return {"destination_search_request": search_request, "destination_candidates": candidates, "completed_agents": ["destination"], "search_relaxations": [relaxation] if relaxation else [], "search_diagnostics": [diagnostic] if diagnostic else [], "messages": [f"관광지 후보 {len(candidates)}개를 찾았습니다."]}

def _build_search_request(state: TravelState) -> SearchRequest:
    return build_search_request(state, PlaceDomain.DESTINATION, "_DESTINATION")
