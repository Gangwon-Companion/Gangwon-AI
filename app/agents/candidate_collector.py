from __future__ import annotations

from app.core.state import AgentName, TravelState


def candidate_collector_node(state: TravelState) -> TravelState:
    """선택된 후보 검색 Agent가 모두 완료됐는지 확인하는 병렬 합류 노드다."""
    selected = set(state.get("selected_agents", []))
    completed = set(state.get("completed_agents", []))
    missing_agents = selected - completed

    if missing_agents:
        names = ", ".join(sorted(missing_agents))
        return {
            "candidates_ready": False,
            "status": "failed",
            "errors": [f"후보 검색 완료 신호가 없습니다: {names}"],
            "messages": ["후보 검색 결과를 모두 수집하지 못했습니다."],
        }

    candidate_counts: dict[AgentName, int] = {
        "destination": len(state.get("destination_candidates", [])),
        "restaurant": len(state.get("restaurant_candidates", [])),
        "lodging": len(state.get("lodging_candidates", [])),
    }
    summary = ", ".join(
        f"{agent} {candidate_counts.get(agent, 0)}개" for agent in sorted(selected)
    )
    return {
        "candidates_ready": True,
        "status": "running",
        "messages": [f"전문 Agent 후보 수집을 완료했습니다: {summary}"],
    }
