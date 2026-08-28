from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.agents.candidate_collector import candidate_collector_node
from app.agents.destination import destination_node
from app.agents.input_parser import (
    conflict_checker_node,
    form_binder_node,
    preference_extractor_node,
)
from app.agents.lodging import lodging_node
from app.agents.itinerary import itinerary_node
from app.agents.restaurant import restaurant_node
from app.agents.response import response_node
from app.agents.supervisor import (
    candidate_retry_node,
    supervisor_node,
    validation_retry_node,
)
from app.agents.validation import validation_node
from app.core.state import TravelState
from app.validators.hard_validator import hard_validator_node

# 그래프에 실제로 등록된 하위 Agent다. 팀에서 Agent를 추가할 때
# add_node와 함께 여기에도 이름을 넣으면 Supervisor의 계획에 자동으로 반영된다.
IMPLEMENTED_AGENT_NODES = {"destination", "lodging", "restaurant"}


def _route_after_conflict_checker(state: TravelState) -> str:
    return "supervisor" if state.get("input_complete") else END


# Supervisor가 만든 execution_plan을 읽어 병렬 Agent로 분배한다.
# 라우팅 조건을 노드 이름으로 하드코딩하지 않으므로 Agent가 늘어도 이 함수는 그대로 둔다.
def _dispatch_agents(state: TravelState):
    targets = [
        step["agent"]
        for step in state.get("execution_plan", [])
        if step.get("mode") == "parallel" and step["agent"] in IMPLEMENTED_AGENT_NODES
    ]
    if not targets:
        return END
    return [Send(agent, state) for agent in targets]


def _route_after_candidate_collector(state: TravelState) -> str:
    return "itinerary" if state.get("candidates_ready") else END


def _route_after_itinerary(state: TravelState) -> str:
    return "validator" if state.get("itinerary_status") == "READY" else "candidate_retry"


def _route_after_validator(state: TravelState) -> str:
    return (
        "validation"
        if state.get("hard_validation", {}).get("status") == "VALID"
        else "validation_retry"
    )


def _route_after_validation(state: TravelState) -> str:
    return (
        "response"
        if state.get("quality_validation", {}).get("status") == "PASS"
        else "validation_retry"
    )


def _dispatch_retry_agents(state: TravelState):
    if state.get("status") == "failed":
        return "response"
    targets = [
        agent
        for agent in state.get("retry_agents", [])
        if agent in IMPLEMENTED_AGENT_NODES
    ]
    if not targets:
        return "response"
    return [Send(agent, state) for agent in targets]


def _dispatch_validation_retry(state: TravelState):
    if state.get("status") == "failed":
        return "response"

    actions = state.get("retry_actions", [])
    targets = list(
        dict.fromkeys(
            action.get("agent")
            for action in actions
            if action.get("agent") in IMPLEMENTED_AGENT_NODES
        )
    )
    if targets:
        return [Send(agent, state) for agent in targets]
    if any(action.get("agent") == "itinerary" for action in actions):
        return "itinerary"
    return "response"


# 후보 검색 Agent를 병렬 실행한 뒤 Candidate Collector에서 합류하고 일정을 구성한다.
def build_graph():
    builder = StateGraph(TravelState)
    builder.add_node("form_binder", form_binder_node)
    builder.add_node("preference_extractor", preference_extractor_node)
    builder.add_node("conflict_checker", conflict_checker_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("destination", destination_node)
    builder.add_node("lodging", lodging_node)
    builder.add_node("restaurant", restaurant_node)
    builder.add_node("candidate_collector", candidate_collector_node)
    builder.add_node("itinerary", itinerary_node)
    builder.add_node("candidate_retry", candidate_retry_node)
    builder.add_node("validator", hard_validator_node)
    builder.add_node("validation", validation_node)
    builder.add_node("validation_retry", validation_retry_node)
    builder.add_node("response", response_node)

    builder.add_edge(START, "form_binder")
    builder.add_edge("form_binder", "preference_extractor")
    builder.add_edge("preference_extractor", "conflict_checker")
    builder.add_conditional_edges(
        "conflict_checker",
        _route_after_conflict_checker,
        ["supervisor", END],
    )
    builder.add_conditional_edges("supervisor", _dispatch_agents)
    builder.add_edge("destination", "candidate_collector")
    builder.add_edge("lodging", "candidate_collector")
    builder.add_edge("restaurant", "candidate_collector")
    builder.add_conditional_edges(
        "candidate_collector",
        _route_after_candidate_collector,
        ["itinerary", END],
    )
    builder.add_conditional_edges(
        "itinerary",
        _route_after_itinerary,
        ["validator", "candidate_retry"],
    )
    builder.add_conditional_edges("candidate_retry", _dispatch_retry_agents)
    builder.add_conditional_edges(
        "validator",
        _route_after_validator,
        ["validation", "validation_retry"],
    )
    builder.add_conditional_edges(
        "validation",
        _route_after_validation,
        ["response", "validation_retry"],
    )
    builder.add_conditional_edges("validation_retry", _dispatch_validation_retry)
    builder.add_edge("response", END)
    return builder.compile()


travel_graph = build_graph().with_config({"recursion_limit": 50})
