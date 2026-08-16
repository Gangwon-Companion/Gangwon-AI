from langgraph.graph import END, START, StateGraph

from app.agents.input_parser import conflict_checker_node, preference_extractor_node
from app.agents.supervisor import supervisor_node
from app.agents.destination import destination_node
from app.core.state import TravelState


def _route_after_supervisor(state: TravelState) -> str:
    if "destination" in state.get("selected_agents", []):
        return "destination"
    return END


# Supervisor의 Agent 선택 결과에 따라 Destination Agent를 실행하는 LangGraph를 생성한다.
def build_graph():
    builder = StateGraph(TravelState)
    builder.add_node("preference_extractor", preference_extractor_node)
    builder.add_node("conflict_checker", conflict_checker_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_node("destination", destination_node)
    builder.add_edge(START, "preference_extractor")
    builder.add_edge("preference_extractor", "conflict_checker")
    builder.add_conditional_edges(
        "conflict_checker",
        lambda state: "supervisor" if state.get("input_complete") else END,
    )
    builder.add_conditional_edges("supervisor", _route_after_supervisor)
    builder.add_edge("destination", END)
    return builder.compile()


travel_graph = build_graph()
