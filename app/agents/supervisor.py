from __future__ import annotations

from app.core.state import AgentName, TravelState


BASE_PARALLEL_AGENTS: list[AgentName] = ["destination", "restaurant", "lodging"]
MAX_VALIDATION_RETRIES = 3
MAX_ITINERARY_RETRIES = 3


# 여행 일수만큼 슬롯을 전개한다. Itinerary Agent가 슬롯 단위로 후보를 모으므로
# 하루치 슬롯만 만들면 2일차 이후 일정을 구성할 수 없다.
def _slots(days: int, has_activity: bool) -> list[str]:
    slots: list[str] = []
    for day in range(1, days + 1):
        if day > 1:
            slots.append(f"D{day}_BREAKFAST")
        slots.append(f"D{day}_DESTINATION")
        slots.append(f"D{day}_LUNCH")
        if has_activity:
            slots.append(f"D{day}_ACTIVITY")
        slots.append(f"D{day}_DINNER")
        if day < days:
            slots.append(f"D{day}_LODGING")
    return slots


# 구조화된 요청과 선호 프로필을 근거로 Agent 선택과 실행 순서를 결정한다.
# 자연어 해석은 앞단(FormBinder, PreferenceExtractor)에서 끝난 상태다.
def supervisor_node(state: TravelState) -> TravelState:
    request = state["request"]
    profile = state.get("preference_profile", {})
    days = request.get("travel_days") or 1
    activity_requested = bool(profile.get("activity_requested"))

    # 당일치기면 숙박 슬롯이 없으므로 Lodging Agent도 호출하지 않는다.
    selected: list[AgentName] = [
        agent for agent in BASE_PARALLEL_AGENTS if agent != "lodging" or days > 1
    ]
    if activity_requested:
        selected.append("activity")

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
    if activity_requested:
        messages.append("체험/액티비티 요청이 있어 Activity Agent를 추가했습니다.")

    return {
        "slots": _slots(days, activity_requested),
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
