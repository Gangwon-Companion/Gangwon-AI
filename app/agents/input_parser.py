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
_DAY_TRIP_KEYWORDS = ("당일치기", "당일 여행")

_PET_KEYWORDS = ("반려견", "반려동물", "반려묘", "강아지", "댕댕이", "애견", "고양이")
_PET_SIZE_KEYWORDS = {"소형견": "SMALL", "중형견": "MEDIUM", "대형견": "LARGE"}
_WHEELCHAIR_KEYWORDS = ("휠체어", "무장애", "배리어프리")
_INDOOR_PET_KEYWORDS = ("실내 동반", "실내동반", "실내 반려동물", "실내 애견")

# 한국어는 부정어가 키워드 뒤에 온다. 창을 좁게 잡아야 "반려동물 동반 가능한 숙소 없나요"의
# 뒤쪽 "없"을 부정으로 오인하지 않는다. "안"은 "안고"와 겹치므로 뒤에 공백을 요구한다.
_NEGATION_MARKERS = ("없", "안 ", "미동반", "아니", "제외", "말고", "빼고", "불가")
_NEGATION_WINDOW = 6

# 선호 키워드를 Search Tool이 쓰는 soft preference 이름과 가중치로 매핑한다.
_PREFERENCE_KEYWORDS: dict[str, tuple[str, float]] = {
    "카페": ("cafe", 0.8),
    "바다": ("oceanView", 0.9),
    "조용한": ("quiet", 0.9),
    "맛집": ("food", 0.8),
    "자연": ("nature", 0.8),
    "야경": ("nightView", 0.7),
    "체험": ("activity", 0.8),
    "레저": ("activity", 0.8),
}

_ACTIVITY_KEYWORDS = ("액티비티", "체험", "레저", "activity", "experience")

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
    return (int(match.group(1)), None) if match else (None, None)


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
    keywords = list(request.get("preferences", []))

    for keyword in _PREFERENCE_KEYWORDS:
        if keyword in message and keyword not in keywords:
            keywords.append(keyword)
    request["preferences"] = keywords

    soft: dict[str, float] = {}
    for keyword in keywords:
        mapped = _PREFERENCE_KEYWORDS.get(keyword)
        if mapped is None:
            continue
        name, weight = mapped
        soft[name] = max(soft.get(name, 0.0), weight)

    # Activity 의도를 여기서 한 번만 판정해 Supervisor가 원문을 다시 읽지 않게 한다.
    activity_requested = any(keyword in message for keyword in _ACTIVITY_KEYWORDS) or any(
        keyword in keywords for keyword in ("액티비티", "체험", "레저")
    )

    return {
        "request": request,
        "preference_profile": {
            "keywords": keywords,
            "soft": soft,
            "activity_requested": activity_requested,
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
