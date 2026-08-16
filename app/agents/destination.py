from __future__ import annotations

from dataclasses import dataclass

from app.core.state import DestinationCandidate, TravelState


@dataclass(frozen=True)
class SearchRequest:
    type: str
    query: str
    region: str | None
    filters: dict[str, object]


_THEME_KEYWORDS: dict[str, str] = {
    "자연": "NA",
    "바다": "NA",
    "해변": "NA",
    "역사": "HS",
    "문화": "HS",
    "체험": "EX",
    "레저": "LS",
    "시장": "SH",
    "축제": "EV",
    "이벤트": "EV",
}

_CONTENT_TYPE_KEYWORDS: dict[str, int] = {
    "관광지": 12,
    "해변": 12,
    "공원": 12,
    "박물관": 14,
    "문화": 14,
    "역사": 14,
    "축제": 15,
    "이벤트": 15,
    "체험": 28,
    "레저": 28,
}

_PET_FEATURE_KEYWORDS = ("동반", "목줄", "케이지", "실내", "야외", "배변봉투")
_ACCESSIBILITY_FEATURE_KEYWORDS = ("주차", "화장실", "휠체어", "엘리베이터", "경사로", "안내")


def destination_node(state: TravelState) -> TravelState:
    search_request = _build_search_request(state)
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


def _build_search_request(state: TravelState) -> SearchRequest:
    # 공통 Search Tool이 받을 수 있도록 사용자 요청에서 목적지 검색 조건만 추린다.
    request = state["request"]
    profile = state.get("preference_profile", {})
    keywords = profile.get("keywords") or request.get("preferences", [])
    filters: dict[str, object] = {}

    theme_code = _resolve_theme_code(keywords)
    if theme_code:
        filters["themeCode"] = theme_code
    content_type_id = _resolve_content_type_id(keywords)
    if content_type_id:
        filters["contentTypeId"] = content_type_id
    if request.get("wheelchair_accessible"):
        filters["accessibility"] = True
    if request.get("pet_allowed"):
        filters["pet"] = True

    filters["features"] = _build_feature_filters(keywords, str(request.get("message") or ""))

    query = " ".join([*keywords, "관광지"]).strip()
    return SearchRequest(
        type="DESTINATION",
        query=query or str(request.get("message") or "관광지").strip(),
        region=request.get("region"),
        filters=filters,
    )


def _resolve_theme_code(keywords: list[str]) -> str | None:
    for keyword in keywords:
        if keyword in _THEME_KEYWORDS:
            return _THEME_KEYWORDS[keyword]
    return None


def _resolve_content_type_id(keywords: list[str]) -> int | None:
    for keyword in keywords:
        if keyword in _CONTENT_TYPE_KEYWORDS:
            return _CONTENT_TYPE_KEYWORDS[keyword]
    return None


def _build_feature_filters(keywords: list[str], message: str) -> dict[str, list[str]]:
    text = " ".join([*keywords, message])
    pet_features = [keyword for keyword in _PET_FEATURE_KEYWORDS if keyword in text]
    accessibility_features = [
        keyword for keyword in _ACCESSIBILITY_FEATURE_KEYWORDS if keyword in text
    ]
    return {
        "pet": pet_features,
        "accessibility": accessibility_features,
    }


def _search_destinations(search_request: SearchRequest) -> list[DestinationCandidate]:
    # TODO: 공통 Search Tool이 구현되면 이 Mock 검색을 실제 검색 호출로 교체한다.
    region = search_request.region or "강원"
    filters = search_request.filters
    matched_conditions = ["region"]
    if search_request.query:
        matched_conditions.append("query")
    for key in ("themeCode", "contentTypeId", "pet", "accessibility"):
        if filters.get(key):
            matched_conditions.append(key)
    features = filters.get("features", {})
    if isinstance(features, dict):
        if features.get("pet"):
            matched_conditions.append("features.pet")
        if features.get("accessibility"):
            matched_conditions.append("features.accessibility")

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
    return mock_candidates[:5]
