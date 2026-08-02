from __future__ import annotations

from app.core.state import TravelState

# Spring Boot가 정규화한 요청에서 선호 키워드를 보완한다.
def preference_extractor_node(state: TravelState) -> TravelState:
    request = dict(state["request"])
    message = request.get("message", "").lower()
    preferences = list(request.get("preferences", []))
    keywords = ("카페", "바다", "조용한", "맛집", "체험", "레저", "자연", "야경")

    for keyword in keywords:
        if keyword in message and keyword not in preferences:
            preferences.append(keyword)
    request["preferences"] = preferences
    return {"request": request}


# 필수 정보 누락과 입력 간 충돌을 확인한다.
def conflict_checker_node(state: TravelState) -> TravelState:
    request = state["request"]
    missing_fields: list[str] = []
    questions: list[str] = []
    conflicts: list[str] = []

    if request.get("pet_allowed") is False and request.get("pet_size"):
        conflicts.append("반려동물 미동반인데 반려동물 크기가 입력되었습니다.")
        questions.append("반려동물 동반 여부와 크기 정보를 확인해주세요.")
    if request.get("nights") is not None and request.get("travel_days"):
        if request["nights"] != request["travel_days"] - 1:
            conflicts.append("숙박 일수와 여행 일수가 일치하지 않습니다.")
            questions.append("여행 일수와 숙박 일수를 확인해주세요.")

    complete = not missing_fields and not conflicts
    messages = ["Spring Boot 정규화 요청의 PreferenceExtractor와 ConflictChecker를 완료했습니다."]
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
        "retry_count": 0,
        "messages": messages,
    }
