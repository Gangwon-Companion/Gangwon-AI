from app.core.state import DestinationCandidate, TravelState
from app.search.be_client import search_client
from app.search.client import SearchClientError
from app.search.models import PlaceDomain, SearchRequest
from app.search.request_factory import build_search_request

def destination_node(state: TravelState) -> TravelState:
    search_request = _build_search_request(state)
    try:
        response = search_client.search(search_request)
    except SearchClientError as exc:
        return {"destination_search_request": search_request, "destination_candidates": [], "completed_agents": ["destination"], "errors": [str(exc)], "messages": ["관광지 검색 서비스 호출에 실패했습니다."]}
    candidates: list[DestinationCandidate] = []
    for item in response.results:
        candidates.append({"destination_id": int(item.place_id.split(":", 1)[1]), "title": item.name, "addr1": item.address or "", "map_x": item.location.lon if item.location else 0.0, "map_y": item.location.lat if item.location else 0.0, "theme_code": "", "source_types": sorted({e.source for e in item.evidence}), "score": item.score, "reason": "검색어와 선호조건을 기준으로 선정한 관광지 후보입니다.", "matched_conditions": item.matched_preferences})
    return {"destination_search_request": search_request, "destination_candidates": candidates, "completed_agents": ["destination"], "messages": [f"관광지 후보 {len(candidates)}개를 찾았습니다."]}

def _build_search_request(state: TravelState) -> SearchRequest:
    return build_search_request(state, PlaceDomain.DESTINATION, "_DESTINATION")
