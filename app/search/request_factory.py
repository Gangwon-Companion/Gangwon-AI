from app.core.state import TravelState
from app.search.models import HardFilters, PlaceDomain, SearchRequest
from app.search.regions import region_code_for

def build_search_request(state: TravelState, domain: PlaceDomain, slot_suffix: str) -> SearchRequest:
    request = state["request"]
    profile = state.get("preference_profile", {})
    region_code = region_code_for(request.get("region"))
    slot = next((value for value in state.get("slots", []) if value.endswith(slot_suffix)), slot_suffix)
    return SearchRequest(domain=domain, slot=slot, region_codes=[region_code] if region_code else [], query_text=" ".join(profile.get("keywords", [])).strip(), hard_filters=HardFilters(pet_allowed=request.get("pet_allowed"), pet_size=request.get("pet_size"), wheelchair_accessible=request.get("wheelchair_accessible")), soft_preferences=dict(profile.get("soft", {})), limit=5)
