from langgraph.graph import END, START, StateGraph

from app.agents.input_parser import conflict_checker_node, preference_extractor_node
from app.agents.supervisor import supervisor_node
from app.core.state import TravelState


# Supervisor 노드만 연결한 초기 LangGraph를 생성한다.
def build_graph():
    builder = StateGraph(TravelState)
    builder.add_node("preference_extractor", preference_extractor_node)
    builder.add_node("conflict_checker", conflict_checker_node)
    builder.add_node("supervisor", supervisor_node)
    builder.add_edge(START, "preference_extractor")
    builder.add_edge("preference_extractor", "conflict_checker")
    builder.add_conditional_edges(
        "conflict_checker",
        lambda state: "supervisor" if state.get("input_complete") else END,
    )
    builder.add_edge("supervisor", END)
    return builder.compile()


travel_graph = build_graph()
