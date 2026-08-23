from app.core.state import TravelRequest, TravelState
from app.search.models import HardFilters, PlaceDomain, SearchRequest
from app.search.regions import region_code_for


_DOMAIN_KEYWORDS: dict[PlaceDomain, set[str]] = {
    PlaceDomain.DESTINATION: {"바다", "자연", "야경", "체험", "레저", "산책", "관광지"},
    PlaceDomain.RESTAURANT: {"카페", "맛집", "한식", "음식", "식당", "커피", "해산물", "순두부"},
    PlaceDomain.LODGING: {"바다", "조용한", "숙소", "호텔", "펜션", "리조트", "민박", "게스트하우스", "오션뷰"},
}

_DOMAIN_PREFERENCES: dict[PlaceDomain, set[str]] = {
    PlaceDomain.DESTINATION: {"quiet", "ocean_view", "oceanView", "nature", "nightView"},
    PlaceDomain.RESTAURANT: {"quiet", "ocean_view", "oceanView", "cafe", "food"},
    PlaceDomain.LODGING: {"quiet", "ocean_view", "oceanView", "nature"},
}


def build_search_request(state: TravelState, domain: PlaceDomain, slot_suffix: str) -> SearchRequest:
    request = state["request"]
    profile = state.get("preference_profile", {})
    region_code = region_code_for(request.get("region"))
    slot = next((value for value in state.get("slots", []) if value.endswith(slot_suffix)), slot_suffix)
    return SearchRequest(
        domain=domain,
        slot=slot,
        region_codes=[region_code] if region_code else [],
        query_text=" ".join(_keywords_for(domain, profile.get("keywords", []))),
        hard_filters=HardFilters(
            pet_allowed=request.get("pet_allowed"),
            pet_size=request.get("pet_size"),
            wheelchair_accessible=request.get("wheelchair_accessible"),
        ),
        soft_preferences=_preferences_for(domain, profile.get("soft", {})),
        limit=_candidate_limit(request, domain),
    )


def _keywords_for(domain: PlaceDomain, keywords: list[str]) -> list[str]:
    classified = set().union(*_DOMAIN_KEYWORDS.values())
    allowed = _DOMAIN_KEYWORDS[domain]
    return [keyword for keyword in keywords if keyword in allowed or keyword not in classified]


def _preferences_for(domain: PlaceDomain, preferences: dict[str, float]) -> dict[str, float]:
    classified = set().union(*_DOMAIN_PREFERENCES.values())
    allowed = _DOMAIN_PREFERENCES[domain]
    return {
        key: value
        for key, value in preferences.items()
        if key in allowed or key not in classified
    }


def _candidate_limit(request: TravelRequest, domain: PlaceDomain) -> int:
    days = max(1, request.get("travel_days") or 1)
    if domain == PlaceDomain.DESTINATION:
        return min(days * 5, 30)
    if domain == PlaceDomain.RESTAURANT:
        return min(days * 8, 40)
    nights = request.get("nights")
    return min(max(nights if nights is not None else days - 1, 1) * 5, 20)
