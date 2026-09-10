from app.core.state import SearchDiagnostic, SearchRelaxation, TravelRequest, TravelState
from app.search.models import HardFilters, PlaceDomain, RegionCode, SearchRequest
from app.search.regions import region_code_for


_DOMAIN_KEYWORDS: dict[PlaceDomain, set[str]] = {
    PlaceDomain.DESTINATION: {
        "바다", "해변", "해수욕장", "동해바다", "일출", "노을", "석양", "자연",
        "산", "숲", "계곡", "호수", "폭포", "산책", "트레킹", "등산", "전망",
        "전망대", "드라이브", "야경", "밤바다", "실내", "야외", "비오는날", "체험",
        "레저", "액티비티", "서핑", "스키", "스노보드", "케이블카", "레일바이크",
        "낚시", "온천", "목장", "박물관", "전시", "관광지",
    },
    PlaceDomain.RESTAURANT: {
        "카페", "커피", "디저트", "빵집", "맛집", "로컬맛집", "음식", "식당",
        "해산물", "회", "물회", "생선", "대게", "홍게", "조개", "조개구이",
        "막국수", "순두부", "초당순두부", "닭갈비", "한식", "양식", "중식", "일식",
        "시장", "전통시장",
    },
    PlaceDomain.LODGING: {
        "바다", "해변", "오션뷰", "오션뷰숙소", "조용한", "한적한", "여유로운",
        "힐링", "감성", "가족", "커플", "아이와", "부모님", "숙소", "호텔", "펜션",
        "리조트", "풀빌라", "캠핑", "글램핑", "민박", "게스트하우스",
    },
}

_DOMAIN_PREFERENCES: dict[PlaceDomain, set[str]] = {
    PlaceDomain.DESTINATION: {"quiet", "ocean_view", "oceanView", "nature", "nightView"},
    PlaceDomain.RESTAURANT: {"quiet", "ocean_view", "oceanView", "cafe", "food"},
    PlaceDomain.LODGING: {"quiet", "ocean_view", "oceanView", "nature"},
}

_EAST_COAST_REGIONS = [
    RegionCode.GOSEONG,
    RegionCode.SOKCHO,
    RegionCode.YANGYANG,
    RegionCode.GANGNEUNG,
    RegionCode.DONGHAE,
    RegionCode.SAMCHEOK,
]

_EAST_COAST_NEIGHBORS: dict[RegionCode, list[RegionCode]] = {
    RegionCode.GOSEONG: [RegionCode.GOSEONG, RegionCode.SOKCHO],
    RegionCode.SOKCHO: [RegionCode.GOSEONG, RegionCode.SOKCHO, RegionCode.YANGYANG],
    RegionCode.YANGYANG: [RegionCode.SOKCHO, RegionCode.YANGYANG, RegionCode.GANGNEUNG],
    RegionCode.GANGNEUNG: [RegionCode.YANGYANG, RegionCode.GANGNEUNG, RegionCode.DONGHAE],
    RegionCode.DONGHAE: [RegionCode.GANGNEUNG, RegionCode.DONGHAE, RegionCode.SAMCHEOK],
    RegionCode.SAMCHEOK: [RegionCode.DONGHAE, RegionCode.SAMCHEOK],
}


def build_search_request(state: TravelState, domain: PlaceDomain, slot_suffix: str) -> SearchRequest:
    request = state["request"]
    profile = state.get("preference_profile", {})
    region_code = region_code_for(request.get("region"))
    slot = next((value for value in state.get("slots", []) if value.endswith(slot_suffix)), slot_suffix)
    retry_count = state.get("retry_count", 0)
    diagnostics = _latest_diagnostics_for_domain(state, domain)
    return SearchRequest(
        domain=domain,
        slot=slot,
        region_codes=_region_codes(region_code, profile, domain, request, retry_count, diagnostics),
        query_text=_query_text_for(domain, profile.get("keywords", []), retry_count, diagnostics),
        hard_filters=_hard_filters_for(domain, request),
        soft_preferences=_preferences_for(domain, profile.get("soft", {})),
        limit=_candidate_limit(request, domain, retry_count, diagnostics),
    )


def _region_codes(
    region_code: RegionCode | None,
    profile: dict,
    domain: PlaceDomain,
    request: TravelRequest,
    retry_count: int = 0,
    diagnostics: SearchDiagnostic | None = None,
) -> list[RegionCode]:
    if region_code:
        if domain == PlaceDomain.RESTAURANT:
            return _restaurant_region_codes(region_code, retry_count, diagnostics)
        return [region_code]
    soft = profile.get("soft", {})
    keywords = profile.get("keywords", [])
    if domain != PlaceDomain.RESTAURANT and (
        "oceanView" in soft or "ocean_view" in soft or "바다" in keywords
    ):
        return list(_EAST_COAST_REGIONS)
    return []


def _keywords_for(domain: PlaceDomain, keywords: list[str]) -> list[str]:
    classified = set().union(*_DOMAIN_KEYWORDS.values())
    allowed = _DOMAIN_KEYWORDS[domain]
    return [keyword for keyword in keywords if keyword in allowed or keyword not in classified]


def _query_text_for(
    domain: PlaceDomain,
    keywords: list[str],
    retry_count: int,
    diagnostics: SearchDiagnostic | None = None,
) -> str:
    base_keywords = _keywords_for(domain, keywords)
    if retry_count <= 0:
        return " ".join(base_keywords)
    diagnostic_strategy = _diagnostic_query_strategy(diagnostics)
    if diagnostic_strategy == "DROP_QUERY_TEXT":
        return ""
    if diagnostic_strategy == "EXPAND_QUERY_TEXT":
        return " ".join(_relaxed_keywords(base_keywords, 1, _generic_keywords(domain)))
    if domain == PlaceDomain.RESTAURANT:
        return " ".join(_relaxed_keywords(base_keywords, retry_count, ["맛집", "음식", "식당"]))
    if domain == PlaceDomain.DESTINATION:
        return " ".join(_relaxed_keywords(base_keywords, retry_count, ["관광지", "산책"]))
    if domain == PlaceDomain.LODGING:
        return " ".join(_relaxed_keywords(base_keywords, retry_count, ["숙소"]))
    return " ".join(base_keywords)


def build_search_relaxation(
    state: TravelState, domain: PlaceDomain, slot_suffix: str
) -> SearchRelaxation | None:
    retry_count = state.get("retry_count", 0)
    if retry_count <= 0:
        return None

    profile = state.get("preference_profile", {})
    request = state["request"]
    region_code = region_code_for(request.get("region"))
    original_query = " ".join(_keywords_for(domain, profile.get("keywords", [])))
    diagnostics = _latest_diagnostics_for_domain(state, domain)
    used_query = _query_text_for(domain, profile.get("keywords", []), retry_count, diagnostics)
    original_regions = [region_code] if region_code else []
    used_regions = _region_codes(region_code, profile, domain, request, retry_count, diagnostics)
    if original_query == used_query and original_regions == used_regions:
        return None

    slot = next((value for value in state.get("slots", []) if value.endswith(slot_suffix)), slot_suffix)
    strategy = _relaxation_strategy(retry_count, diagnostics, original_regions, used_regions)
    agent = _agent_for_domain(domain)
    return {
        "agent": agent,
        "domain": domain.value,
        "slot": slot,
        "retry_count": retry_count,
        "original_query": original_query,
        "used_query": used_query,
        "original_regions": [region.value for region in original_regions],
        "used_regions": [region.value for region in used_regions],
        "strategy": strategy,
        "reason": _relaxation_reason(
            domain, original_query, used_query, strategy, original_regions, used_regions
        ),
        "source": "diagnostics" if diagnostics else "retry_ladder",
        "failure_reasons": diagnostics.get("failure_reasons", []) if diagnostics else [],
        "suggested_actions": diagnostics.get("suggested_actions", []) if diagnostics else [],
    }


def build_search_diagnostic(
    state: TravelState, domain: PlaceDomain, slot_suffix: str, diagnostics
) -> SearchDiagnostic | None:
    if diagnostics is None:
        return None

    slot = next((value for value in state.get("slots", []) if value.endswith(slot_suffix)), slot_suffix)
    return {
        "agent": _agent_for_domain(domain),
        "domain": domain.value,
        "slot": slot,
        "retry_count": state.get("retry_count", 0),
        "requested_limit": diagnostics.requested_limit,
        "returned_count": diagnostics.returned_count,
        "unique_count": diagnostics.unique_count,
        "shortage": diagnostics.shortage,
        "failure_reasons": list(diagnostics.failure_reasons),
        "under_matched_preferences": list(diagnostics.under_matched_preferences),
        "unmatched_query_terms": list(diagnostics.unmatched_query_terms),
        "missing_evidence_fields": list(diagnostics.missing_evidence_fields),
        "counts": dict(diagnostics.counts),
        "suggested_actions": list(diagnostics.suggested_actions),
    }


def _relaxed_keywords(base_keywords: list[str], retry_count: int, generic_keywords: list[str]) -> list[str]:
    if retry_count == 1:
        return list(dict.fromkeys([*base_keywords, *generic_keywords]))
    if retry_count == 2:
        return generic_keywords
    return []


def _hard_filters_for(domain: PlaceDomain, request: TravelRequest) -> HardFilters:
    if domain != PlaceDomain.DESTINATION:
        return HardFilters()
    return HardFilters(
        pet_allowed=request.get("pet_allowed"),
        pet_size=request.get("pet_size"),
        wheelchair_accessible=request.get("wheelchair_accessible"),
    )


def _restaurant_region_codes(
    region_code: RegionCode,
    retry_count: int,
    diagnostics: SearchDiagnostic | None,
) -> list[RegionCode]:
    if region_code not in _EAST_COAST_REGIONS:
        return [region_code]
    if retry_count <= 1 and not _should_expand_region(diagnostics):
        return [region_code]
    if retry_count <= 2:
        return _EAST_COAST_NEIGHBORS[region_code]
    return list(_EAST_COAST_REGIONS)


def _should_expand_region(diagnostics: SearchDiagnostic | None) -> bool:
    if not diagnostics:
        return False
    reasons = set(diagnostics.get("failure_reasons", []))
    actions = set(diagnostics.get("suggested_actions", []))
    return bool(
        "EXPAND_REGION" in actions
        or "NO_REGION_MATCH" in reasons
        or "NOT_ENOUGH_UNIQUE_CANDIDATES" in reasons
        or "LOW_RESULT_COUNT" in reasons
    )


def _generic_keywords(domain: PlaceDomain) -> list[str]:
    if domain == PlaceDomain.RESTAURANT:
        return ["맛집", "음식", "식당"]
    if domain == PlaceDomain.DESTINATION:
        return ["관광지", "산책"]
    return ["숙소"]


def _relaxation_strategy(
    retry_count: int,
    diagnostics: SearchDiagnostic | None = None,
    original_regions: list[RegionCode] | None = None,
    used_regions: list[RegionCode] | None = None,
) -> str:
    if original_regions is not None and used_regions is not None and original_regions != used_regions:
        if len(used_regions) == len(_EAST_COAST_REGIONS):
            return "EXPAND_TO_COASTAL_REGION"
        return "EXPAND_TO_NEARBY_REGION"
    diagnostic_strategy = _diagnostic_query_strategy(diagnostics)
    if diagnostic_strategy:
        return diagnostic_strategy
    if retry_count == 1:
        return "EXPAND_QUERY_TEXT"
    if retry_count == 2:
        return "GENERIC_DOMAIN_QUERY"
    return "DROP_QUERY_TEXT_KEEP_REGION"


def _diagnostic_query_strategy(diagnostics: SearchDiagnostic | None) -> str | None:
    if not diagnostics:
        return None

    reasons = set(diagnostics.get("failure_reasons", []))
    actions = set(diagnostics.get("suggested_actions", []))
    counts = diagnostics.get("counts", {})
    current = counts.get("current", diagnostics.get("returned_count", 0))
    without_query = counts.get("without_query", 0)

    if "DROP_QUERY_TEXT" in actions:
        return "DROP_QUERY_TEXT"
    if "NO_TEXT_MATCH" in reasons and without_query > current:
        if "EXPAND_QUERY_TEXT" in actions:
            return "EXPAND_QUERY_TEXT"
        return "DROP_QUERY_TEXT"
    if "EXPAND_QUERY_TEXT" in actions:
        return "EXPAND_QUERY_TEXT"
    return None


def _latest_diagnostics_for_domain(
    state: TravelState, domain: PlaceDomain
) -> SearchDiagnostic | None:
    for item in reversed(state.get("search_diagnostics", [])):
        if item.get("domain") == domain.value:
            return item
    return None


def _agent_for_domain(domain: PlaceDomain):
    if domain == PlaceDomain.DESTINATION:
        return "destination"
    if domain == PlaceDomain.RESTAURANT:
        return "restaurant"
    return "lodging"


def _relaxation_reason(
    domain: PlaceDomain,
    original_query: str,
    used_query: str,
    strategy: str,
    original_regions: list[RegionCode] | None = None,
    used_regions: list[RegionCode] | None = None,
) -> str:
    domain_name = {
        PlaceDomain.DESTINATION: "관광지",
        PlaceDomain.RESTAURANT: "음식점",
        PlaceDomain.LODGING: "숙소",
    }[domain]
    if strategy == "EXPAND_QUERY_TEXT":
        return f"{domain_name} 후보가 부족해 '{original_query}' 검색어에 일반 키워드를 추가했습니다."
    if strategy == "GENERIC_DOMAIN_QUERY":
        return f"'{original_query}' 조건과 직접 일치하는 {domain_name} 후보가 부족해 도메인 일반 검색어로 넓혔습니다."
    if strategy == "DROP_QUERY_TEXT":
        return f"검색어 때문에 {domain_name} 후보가 부족하다는 진단에 따라 검색어를 비우고 지역과 필터 중심으로 넓혔습니다."
    if strategy == "EXPAND_TO_NEARBY_REGION":
        return f"{domain_name} 후보가 부족해 요청 지역에서 인접 지역까지 검색 범위를 넓혔습니다."
    if strategy == "EXPAND_TO_COASTAL_REGION":
        return f"{domain_name} 후보가 계속 부족해 동해안 권역 전체로 검색 범위를 넓혔습니다."
    return f"'{original_query}' 조건과 직접 일치하는 {domain_name} 후보가 부족해 지역 중심 검색으로 넓혔습니다."


def _preferences_for(domain: PlaceDomain, preferences: dict[str, float]) -> dict[str, float]:
    classified = set().union(*_DOMAIN_PREFERENCES.values())
    allowed = _DOMAIN_PREFERENCES[domain]
    return {
        key: value
        for key, value in preferences.items()
        if key in allowed or key not in classified
    }


def _candidate_limit(
    request: TravelRequest,
    domain: PlaceDomain,
    retry_count: int = 0,
    diagnostics: SearchDiagnostic | None = None,
) -> int:
    days = max(1, request.get("travel_days") or 1)
    if domain == PlaceDomain.DESTINATION:
        limit = min(days * 5 + retry_count * 5, 30)
        return _diagnostic_limit(limit, diagnostics)
    if domain == PlaceDomain.RESTAURANT:
        limit = min(days * 8 + retry_count * 4, 40)
        return _diagnostic_limit(limit, diagnostics)
    nights = request.get("nights")
    limit = min(max(nights if nights is not None else days - 1, 1) * 5 + retry_count * 3, 20)
    return _diagnostic_limit(limit, diagnostics)


def _diagnostic_limit(base_limit: int, diagnostics: SearchDiagnostic | None) -> int:
    if not diagnostics:
        return base_limit

    reasons = set(diagnostics.get("failure_reasons", []))
    actions = set(diagnostics.get("suggested_actions", []))
    if not ({"INCREASE_LIMIT"} & actions or {"NOT_ENOUGH_UNIQUE_CANDIDATES", "LOW_RESULT_COUNT"} & reasons):
        return base_limit

    requested = diagnostics.get("requested_limit", base_limit)
    shortage = diagnostics.get("shortage", 0)
    increased = max(base_limit, min(100, requested + max(shortage, 20)))
    return increased
