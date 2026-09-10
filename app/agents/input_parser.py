from __future__ import annotations

import re

from app.core.state import TravelState

# 강원도 시군 이름이다. 자연어에 지역이 등장하면 region을 보완하는 데 쓴다.
_KNOWN_REGIONS = (
    "강릉", "속초", "양양", "평창", "춘천", "원주", "동해", "삼척", "정선",
    "홍천", "인제", "고성", "태백", "횡성", "영월", "화천", "양구", "철원",
)

_NIGHTS_DAYS_PATTERN = re.compile(r"(\d+)\s*박\s*(\d+)\s*일")
_DAYS_PATTERN = re.compile(r"(\d+)\s*일")
_DAY_TRIP_KEYWORDS = ("당일치기", "당일 여행", "하루")
_DAY_WORDS = {
    "하루": 1,
    "당일": 1,
    "이틀": 2,
    "사흘": 3,
    "나흘": 4,
}

_PET_KEYWORDS = ("반려견", "반려동물", "반려묘", "강아지", "댕댕이", "애견", "고양이")
_PET_SIZE_KEYWORDS = {"소형견": "SMALL", "중형견": "MEDIUM", "대형견": "LARGE"}
_PET_COMPANION_MARKERS = ("같이", "함께", "동반", "데려", "데리고")
_WHEELCHAIR_KEYWORDS = ("휠체어", "무장애", "배리어프리")
_INDOOR_PET_KEYWORDS = ("실내 동반", "실내동반", "실내 반려동물", "실내 애견")

# 한국어는 부정어가 키워드 뒤에 온다. 창을 좁게 잡아야 "반려동물 동반 가능한 숙소 없나요"의
# 뒤쪽 "없"을 부정으로 오인하지 않는다. "안"은 "안고"와 겹치므로 뒤에 공백을 요구한다.
_NEGATION_MARKERS = ("없", "안 ", "미동반", "아니", "제외", "말고", "빼고", "불가")
_NEGATION_WINDOW = 6
_NEGATIVE_PREFERENCE_MARKERS = ("보다는", "보다", "말고", "빼고", "제외", "적게")
_NEGATIVE_PREFERENCE_WINDOW = 6

# 선호 키워드를 Search Tool이 쓰는 soft preference 이름과 가중치로 매핑한다.
_PREFERENCE_KEYWORDS: dict[str, tuple[str, float]] = {
    "카페": ("cafe", 0.8),
    "커피": ("cafe", 0.75),
    "디저트": ("cafe", 0.7),
    "빵집": ("cafe", 0.7),
    "바다": ("oceanView", 0.9),
    "해변": ("oceanView", 0.85),
    "해수욕장": ("oceanView", 0.85),
    "오션뷰": ("oceanView", 0.9),
    "동해바다": ("oceanView", 0.9),
    "일출": ("oceanView", 0.85),
    "노을": ("oceanView", 0.8),
    "석양": ("oceanView", 0.8),
    "조용한": ("quiet", 0.9),
    "한적한": ("quiet", 0.85),
    "여유로운": ("quiet", 0.8),
    "힐링": ("quiet", 0.8),
    "감성": ("quiet", 0.7),
    "맛집": ("food", 0.8),
    "로컬맛집": ("food", 0.85),
    "음식": ("food", 0.75),
    "식당": ("food", 0.75),
    "해산물": ("food", 0.9),
    "회": ("food", 0.85),
    "물회": ("food", 0.9),
    "생선": ("food", 0.8),
    "대게": ("food", 0.9),
    "홍게": ("food", 0.85),
    "조개": ("food", 0.8),
    "조개구이": ("food", 0.9),
    "막국수": ("food", 0.85),
    "순두부": ("food", 0.85),
    "초당순두부": ("food", 0.9),
    "닭갈비": ("food", 0.85),
    "한식": ("food", 0.8),
    "양식": ("food", 0.75),
    "중식": ("food", 0.75),
    "일식": ("food", 0.75),
    "시장": ("food", 0.7),
    "전통시장": ("food", 0.75),
    "자연": ("nature", 0.8),
    "산": ("nature", 0.8),
    "숲": ("nature", 0.8),
    "계곡": ("nature", 0.85),
    "호수": ("nature", 0.8),
    "폭포": ("nature", 0.8),
    "산책": ("nature", 0.75),
    "트레킹": ("nature", 0.85),
    "등산": ("nature", 0.9),
    "전망": ("nature", 0.8),
    "전망대": ("nature", 0.8),
    "드라이브": ("nature", 0.75),
    "야경": ("nightView", 0.7),
    "밤바다": ("nightView", 0.8),
    "가족": ("quiet", 0.75),
    "커플": ("quiet", 0.75),
    "아이와": ("quiet", 0.85),
    "부모님": ("quiet", 0.85),
    "실내": ("quiet", 0.7),
    "야외": ("nature", 0.7),
    "비오는날": ("quiet", 0.75),
    "관광지": ("nature", 0.75),
    "체험": ("nature", 0.75),
    "레저": ("nature", 0.75),
    "액티비티": ("nature", 0.75),
    "서핑": ("nature", 0.9),
    "스키": ("nature", 0.9),
    "스노보드": ("nature", 0.9),
    "케이블카": ("nature", 0.85),
    "레일바이크": ("nature", 0.85),
    "낚시": ("nature", 0.85),
    "캠핑": ("nature", 0.85),
    "글램핑": ("nature", 0.85),
    "온천": ("quiet", 0.85),
    "목장": ("nature", 0.8),
    "박물관": ("quiet", 0.75),
    "전시": ("quiet", 0.75),
    "호텔": ("quiet", 0.8),
    "펜션": ("quiet", 0.8),
    "리조트": ("quiet", 0.8),
    "풀빌라": ("quiet", 0.85),
    "오션뷰숙소": ("oceanView", 0.9),
}

_REQUIRED_FIELD_QUESTIONS = {
    "region": "어느 지역으로 여행하시나요?",
    "travel_days": "여행 기간이 며칠인가요?",
    "pet_allowed": "반려동물과 함께 가시는지 알려주세요.",
}


# 키워드가 등장했는지와 함께 부정문인지까지 본다. 등장하지 않으면 None(미입력),
# 모든 등장이 부정문이면 False, 하나라도 긍정이면 True다.
# 키워드 유무만 보면 "반려동물은 없어요"가 동반(True)으로 뒤집힌다.
def _detect_flag(message: str, keywords: tuple[str, ...]) -> bool | None:
    mentioned = False
    for keyword in keywords:
        start = message.find(keyword)
        while start != -1:
            mentioned = True
            tail_start = start + len(keyword)
            tail = message[tail_start : tail_start + _NEGATION_WINDOW]
            if not any(marker in tail for marker in _NEGATION_MARKERS):
                return True
            start = message.find(keyword, start + 1)
    return False if mentioned else None


def _extract_region(message: str) -> str | None:
    return next((region for region in _KNOWN_REGIONS if region in message), None)


# 자연어에서 여행 일수와 숙박 일수를 읽는다. 확인되지 않은 값은 None으로 남긴다.
def _extract_duration(message: str) -> tuple[int | None, int | None]:
    match = _NIGHTS_DAYS_PATTERN.search(message)
    if match:
        return int(match.group(2)), int(match.group(1))
    if any(keyword in message for keyword in _DAY_TRIP_KEYWORDS):
        return 1, 0
    match = _DAYS_PATTERN.search(message)
    if match:
        return int(match.group(1)), None
    for keyword, days in _DAY_WORDS.items():
        if keyword in message:
            return days, 0 if days == 1 else None
    return None, None


def _has_pet_companion_context(message: str) -> bool:
    pet_words = (*_PET_KEYWORDS, *_PET_SIZE_KEYWORDS.keys())
    for keyword in pet_words:
        start = message.find(keyword)
        while start != -1:
            context = message[max(0, start - 8) : start + len(keyword) + 12]
            if any(marker in context for marker in _PET_COMPANION_MARKERS):
                return True
            start = message.find(keyword, start + 1)
    return False


def _is_negative_preference(message: str, start: int, end: int) -> bool:
    tail = message[end : end + _NEGATIVE_PREFERENCE_WINDOW]
    if any(marker in tail for marker in _NEGATIVE_PREFERENCE_MARKERS):
        return True
    head = message[max(0, start - _NEGATIVE_PREFERENCE_WINDOW) : start]
    return any(marker in head for marker in ("말고", "빼고", "제외"))


def _extract_preference_keywords(message: str, existing: list[str]) -> list[str]:
    keywords = list(existing)
    occupied: list[range] = []
    matches: list[tuple[int, int, str]] = []
    for keyword in _PREFERENCE_KEYWORDS:
        start = message.find(keyword)
        while start != -1:
            matches.append((start, start + len(keyword), keyword))
            start = message.find(keyword, start + 1)

    for start, end, keyword in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]))):
        if _is_negative_preference(message, start, end):
            continue
        span = range(start, end)
        if any(set(span) & set(used) for used in occupied):
            continue
        occupied.append(span)
        if keyword not in keywords:
            keywords.append(keyword)
    return keywords


# 자연어와 Form 입력을 하나의 표준 요청으로 묶는다(plan.md 0.1).
# Form 값이 우선이고 자연어는 비어 있는 항목만 보완한다.
def form_binder_node(state: TravelState) -> TravelState:
    request = dict(state["request"])
    message = request.get("message", "")
    inferred: list[str] = []

    if not request.get("region"):
        region = _extract_region(message)
        if region:
            request["region"] = region
            inferred.append("region")

    days, nights = _extract_duration(message)
    if not request.get("travel_days") and days is not None:
        request["travel_days"] = days
        inferred.append("travel_days")
    # nights는 자연어에 명시된 경우에만 채운다. travel_days에서 역산하면
    # ConflictChecker가 잡아야 할 불일치를 숨기게 된다.
    if request.get("nights") is None and nights is not None:
        request["nights"] = nights
        inferred.append("nights")

    if request.get("pet_allowed") is None:
        pet_allowed = _detect_flag(message, _PET_KEYWORDS)
        if pet_allowed is None and _has_pet_companion_context(message):
            pet_allowed = True
        if pet_allowed is not None:
            request["pet_allowed"] = pet_allowed
            inferred.append("pet_allowed")
    # 크기 표현도 부정문을 걸러야 한다. "대형견은 없어요"에서 크기를 읽으면
    # 미동반과 크기가 함께 들어와 ConflictChecker가 없는 충돌을 만든다.
    if not request.get("pet_size"):
        size = next(
            (v for k, v in _PET_SIZE_KEYWORDS.items() if _detect_flag(message, (k,))),
            None,
        )
        if size:
            request["pet_size"] = size
            inferred.append("pet_size")
            if request.get("pet_allowed") is None and _has_pet_companion_context(message):
                request["pet_allowed"] = True
                inferred.append("pet_allowed")

    # Form에서 명시적으로 False를 보낸 경우에는 자연어가 True로 덮어쓰지 않는다.
    # 필드가 없거나 None일 때만 자연어로 누락값을 보완한다.
    if request.get("wheelchair_accessible") is None and _detect_flag(
        message, _WHEELCHAIR_KEYWORDS
    ):
        request["wheelchair_accessible"] = True
        inferred.append("wheelchair_accessible")

    if request.get("indoor_pet") is None and _detect_flag(message, _INDOOR_PET_KEYWORDS):
        request["indoor_pet"] = True
        inferred.append("indoor_pet")

    messages = [f"자연어에서 {', '.join(inferred)} 항목을 보완했습니다."] if inferred else []
    return {"request": request, "messages": messages}


# 자연어에서 선호조건을 추출한다(plan.md 0.2).
# Form으로 들어온 선호를 우선하고, 자연어 추출값은 누락분을 보완한다.
def preference_extractor_node(state: TravelState) -> TravelState:
    request = dict(state["request"])
    message = request.get("message", "").lower()
    keywords = _extract_preference_keywords(message, list(request.get("preferences", [])))
    request["preferences"] = keywords

    soft: dict[str, float] = {}
    for keyword in keywords:
        mapped = _PREFERENCE_KEYWORDS.get(keyword)
        if mapped is None:
            continue
        name, weight = mapped
        soft[name] = max(soft.get(name, 0.0), weight)

    return {
        "request": request,
        "preference_profile": {
            "keywords": keywords,
            "soft": soft,
        },
    }


# 필수 정보 누락과 입력 간 충돌을 확인한다(plan.md 0.3).
def conflict_checker_node(state: TravelState) -> TravelState:
    request = state["request"]
    missing_fields: list[str] = []
    conflicts: list[str] = []
    questions: list[str] = []

    if not request.get("region"):
        missing_fields.append("region")
    if not request.get("travel_days"):
        missing_fields.append("travel_days")
    if request.get("pet_allowed") is None:
        missing_fields.append("pet_allowed")
    questions.extend(_REQUIRED_FIELD_QUESTIONS[field] for field in missing_fields)

    if request.get("pet_allowed") is False and request.get("pet_size"):
        conflicts.append("반려동물 미동반인데 반려동물 크기가 입력되었습니다.")
        questions.append("반려동물 동반 여부와 크기 정보를 확인해주세요.")

    nights, travel_days = request.get("nights"), request.get("travel_days")
    if nights is not None and travel_days and nights != travel_days - 1:
        conflicts.append("숙박 일수와 여행 일수가 일치하지 않습니다.")
        questions.append("여행 일수와 숙박 일수를 확인해주세요.")

    complete = not missing_fields and not conflicts
    messages = ["PreferenceExtractor와 ConflictChecker를 완료했습니다."]
    messages.append(
        "필수 정보가 모두 있어 Supervisor Agent로 전달합니다."
        if complete
        else "누락되거나 충돌하는 정보가 있어 추가 확인이 필요합니다."
    )

    return {
        "input_complete": complete,
        "missing_fields": missing_fields,
        "clarification_questions": questions,
        "conflicts": conflicts,
        "status": "running" if complete else "needs_clarification",
        "slots": [],
        "selected_agents": [],
        "execution_plan": [],
        # Supervisor 재진입 시 기존 재시도 횟수를 보존한다.
        "retry_count": state.get("retry_count", 0),
        "messages": messages,
    }
