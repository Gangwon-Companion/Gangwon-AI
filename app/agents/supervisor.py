from __future__ import annotations

import re

from app.core.state import AgentName, TravelState


BASE_PARALLEL_AGENTS: list[AgentName] = ["destination", "restaurant", "lodging"]


# 요청 메시지 또는 명시된 값에서 여행 일수를 계산한다.
def _infer_days(message: str, explicit_days: int | None) -> int:
    if explicit_days and explicit_days > 1:
        return explicit_days
    match = re.search(r"(\d+)\s*박\s*(\d+)\s*일", message)
    if match:
        return int(match.group(2))
    match = re.search(r"(\d+)\s*일", message)
    return int(match.group(1)) if match else (explicit_days or 1)


# 여행 일수와 액티비티 요청을 기준으로 필요한 슬롯을 만든다.
def _slots(days: int, has_activity: bool) -> list[str]:
    result = ["DESTINATION", "LUNCH", "DINNER"]
    if days > 1:
        result.extend(["LODGING", "BREAKFAST"])
    if has_activity:
        result.append("ACTIVITY")
    return result


# 사용자 요청을 분석해 Agent 선택과 실행 순서를 결정한다.
def supervisor_node(state: TravelState) -> TravelState:
    request = state["request"]
    message = request.get("message", "")
    days = _infer_days(message, request.get("travel_days"))
    activity_requested = any(
        keyword in message.lower() for keyword in ("액티비티", "체험", "레저", "activity", "experience")
    )

    selected: list[AgentName] = list(BASE_PARALLEL_AGENTS)
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
        f"{request.get('region', '미지정')} {days}일 여행으로 분류했습니다.",
        "초기 후보 검색 Agent는 병렬 실행하고, 일정 구성 후 검증합니다.",
    ]
    if activity_requested:
        messages.append("체험/액티비티 요청이 있어 Activity Agent를 추가했습니다.")

    return {
        "slots": _slots(days, activity_requested),
        "selected_agents": selected,
        "execution_plan": execution_plan,
        "retry_count": 0,
        "status": "planned",
        "messages": messages,
    }
