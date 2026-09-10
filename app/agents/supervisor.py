from __future__ import annotations

from app.core.state import AgentName, TravelState


BASE_PARALLEL_AGENTS: list[AgentName] = ["destination", "restaurant", "lodging"]
MAX_VALIDATION_RETRIES = 3
MAX_ITINERARY_RETRIES = 3


_CAFE_KEYWORDS = {"카페", "커피", "디저트", "베이커리", "브런치"}
_NEGATIVE_CAFE_PATTERNS = ("카페보다는", "카페보다", "카페 말고", "카페는 빼고", "카페 빼고", "카페 제외")
_MULTI_LODGING_PATTERNS = (
    "매일 다른 숙소",
    "숙소를 여러",
    "숙소 여러",
    "다른 숙소",
    "숙소를 다르게",
    "숙소 다르게",
    "머물 숙소를 다르게",
    "숙박을 다르게",
    "각각 다른 숙소",
    "숙소 이동",
    "옮겨 다니",
)


def _wants_cafe(request: dict[str, object], profile: dict[str, object]) -> bool:
    values: list[str] = []
    values.extend(str(value) for value in request.get("preferences", []) or [])
    values.extend(str(value) for value in profile.get("keywords", []) or [])
    soft = profile.get("soft", {})
    if isinstance(soft, dict):
        values.extend(str(key) for key in soft)
    message = str(request.get("message") or "")
    if any(pattern in message for pattern in _NEGATIVE_CAFE_PATTERNS):
        return False
    return any(keyword in message or keyword in values for keyword in _CAFE_KEYWORDS)


def _wants_multiple_lodgings(request: dict[str, object]) -> bool:
    message = str(request.get("message") or "")
    return any(pattern in message for pattern in _MULTI_LODGING_PATTERNS)


def _has_required_evidence_only_failures(state: TravelState) -> bool:
    validation = state.get("hard_validation", {})
    violations = validation.get("violations", [])
    if validation.get("status") != "INVALID" or not violations:
        return False
    if any(violation.get("code") != "EVIDENCE_MISSING" for violation in violations):
        return False
    evidence_terms = ("petAllowed", "indoorPetAllowed", "wheelchairAccessible")
    return any(
        any(term in str(violation.get("reason") or "") for term in evidence_terms)
        for violation in violations
    )


def _day_slots(day: int, *, include_cafe: bool, message: str) -> list[str]:
    destination = f"D{day}_DESTINATION"
    extra_destination = f"D{day}_EXTRA_DESTINATION"
    lunch = f"D{day}_LUNCH"
    cafe = f"D{day}_CAFE"
    dinner = f"D{day}_DINNER"
    middle = cafe if include_cafe else extra_destination

    cafe_index = message.find("카페") if include_cafe else -1
    lunch_index = message.find("점심")
    dinner_index = message.find("저녁")
    destination_indices = [
        index
        for keyword in ("관광지", "바다", "해변", "산책")
        if (index := message.find(keyword)) >= 0
    ]
    destination_after_cafe = (
        include_cafe
        and cafe_index >= 0
        and any(index > cafe_index for index in destination_indices)
    )

    if include_cafe and 0 <= lunch_index < cafe_index and destination_after_cafe:
        return [lunch, cafe, destination, dinner]
    if any(keyword in message for keyword in ("점심 먹고", "점심부터", "점심 먼저")):
        return [lunch, destination, middle, dinner]
    if 0 <= dinner_index < lunch_index:
        return [destination, dinner, middle, lunch]
    return [destination, lunch, middle, dinner]


# 여행 일수만큼 슬롯을 전개한다. 기본은 점심/저녁과 관광지 1~2개이고,
# 카페처럼 선택적 성격이 강한 슬롯은 사용자 요청이 있을 때만 넣는다.
# 숙소는 기본적으로 한 곳 연박을 가정하고, 사용자가 숙소 이동을 원할 때만 여러 개를 둔다.
def _slots(
    days: int,
    request: dict[str, object] | None = None,
    profile: dict[str, object] | None = None,
) -> list[str]:
    request = request or {}
    profile = profile or {}
    include_cafe = _wants_cafe(request, profile)
    multiple_lodgings = _wants_multiple_lodgings(request)
    message = str(request.get("message") or "")
    slots: list[str] = []
    for day in range(1, days + 1):
        slots.extend(_day_slots(day, include_cafe=include_cafe, message=message))
        if day < days and (day == 1 or multiple_lodgings):
            slots.append(f"D{day}_LODGING")
    return slots


# 구조화된 요청과 선호 프로필을 근거로 Agent 선택과 실행 순서를 결정한다.
# 자연어 해석은 앞단(FormBinder, PreferenceExtractor)에서 끝난 상태다.
def supervisor_node(state: TravelState) -> TravelState:
    request = state["request"]
    days = request.get("travel_days") or 1

    # 당일치기면 숙박 슬롯이 없으므로 Lodging Agent도 호출하지 않는다.
    selected: list[AgentName] = [
        agent for agent in BASE_PARALLEL_AGENTS if agent != "lodging" or days > 1
    ]

    # 하위 Agent의 실제 실행이 아니라 실행 순서와 의존성만 정의한다.
    execution_plan: list[dict[str, object]] = [
        {"agent": agent, "mode": "parallel", "depends_on": []}
        for agent in selected
    ]
    execution_plan.extend(
        [
            {"agent": "itinerary", "mode": "sequential", "depends_on": selected},
            {"agent": "validator", "mode": "sequential", "depends_on": ["itinerary"]},
        ]
    )

    messages = [
        f"{request.get('region') or '미지정'} {days}일 여행으로 분류했습니다.",
        "초기 후보 검색 Agent는 병렬 실행하고, 일정 구성 후 검증합니다.",
    ]
    return {
        "slots": _slots(days, request, state.get("preference_profile", {})),
        "selected_agents": selected,
        "execution_plan": execution_plan,
        # 검증 실패 후 재진입할 때 재시도 횟수가 초기화되면 무한 루프가 된다.
        "retry_count": state.get("retry_count", 0),
        "status": "planned",
        "messages": messages,
    }


def validation_retry_node(state: TravelState) -> TravelState:
    """검증기의 수정 요청을 다음 부분 재실행 계획으로 변환한다."""
    retry_count = state.get("retry_count", 0) + 1
    actions = state.get("retry_actions", [])
    if _has_required_evidence_only_failures(state):
        return {
            "retry_count": retry_count,
            "status": "failed",
            "execution_plan": [],
            "messages": ["필수 조건을 확인할 근거가 부족해 재검색을 반복하지 않고 종료합니다."],
        }
    if retry_count > MAX_VALIDATION_RETRIES:
        return {
            "retry_count": retry_count,
            "status": "failed",
            "execution_plan": [],
            "messages": ["최대 검증 재시도 횟수를 초과했습니다."],
        }

    merged: dict[tuple[AgentName, tuple[str, ...]], list[str]] = {}
    for action in actions:
        agent = action.get("agent", "itinerary")
        slots = tuple(sorted(action.get("slots", [])))
        merged.setdefault((agent, slots), []).append(action.get("instruction", ""))

    execution_plan: list[dict[str, object]] = []
    domain_agents: list[AgentName] = []
    for (agent, slots), instructions in merged.items():
        if agent != "itinerary" and agent not in domain_agents:
            domain_agents.append(agent)
        execution_plan.append(
            {
                "agent": agent,
                "mode": "parallel" if agent != "itinerary" else "sequential",
                "depends_on": [],
                "slots": list(slots),
                "instruction": " ".join(filter(None, instructions)),
            }
        )

    if domain_agents and not any(step["agent"] == "itinerary" for step in execution_plan):
        execution_plan.append(
            {"agent": "itinerary", "mode": "sequential", "depends_on": domain_agents}
        )
    execution_plan.extend(
        [
            {"agent": "validator", "mode": "sequential", "depends_on": ["itinerary"]},
            {"agent": "validation", "mode": "sequential", "depends_on": ["validator"]},
        ]
    )
    return {
        "retry_count": retry_count,
        "status": "planned",
        "execution_plan": execution_plan,
        "messages": [f"검증 결과에 따라 {len(merged)}개 작업을 부분 재실행합니다."],
    }


def candidate_retry_node(state: TravelState) -> TravelState:
    """후보 부족 결과를 읽고 필요한 전문 Agent만 다시 실행하도록 준비한다."""
    retry_count = state.get("retry_count", 0) + 1
    requested_agents = [
        action.get("agent") for action in state.get("retry_actions", [])
    ]
    retry_agents: list[AgentName] = []
    for agent in requested_agents:
        if agent in BASE_PARALLEL_AGENTS and agent not in retry_agents:
            retry_agents.append(agent)

    if retry_count > MAX_ITINERARY_RETRIES:
        return {
            "retry_count": retry_count,
            "retry_agents": [],
            "status": "failed",
            "errors": ["일정 후보 검색의 최대 재시도 횟수를 초과했습니다."],
            "messages": ["후보 부족 문제를 해결하지 못해 일정 생성을 종료합니다."],
        }

    if not retry_agents:
        return {
            "retry_count": retry_count,
            "retry_agents": [],
            "status": "failed",
            "errors": ["재실행할 수 있는 후보 검색 Agent가 없습니다."],
            "messages": ["후보 재검색 대상을 결정하지 못했습니다."],
        }

    return {
        "retry_count": retry_count,
        "retry_agents": retry_agents,
        "status": "running",
        "messages": [
            f"후보 부족으로 {', '.join(retry_agents)} Agent를 재실행합니다. "
            f"({retry_count}/{MAX_ITINERARY_RETRIES})"
        ],
    }
