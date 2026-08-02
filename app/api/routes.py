from fastapi import APIRouter

from app.graph import travel_graph
from app.schemas.travel import AgentStep, TravelPlanRequest, TravelPlanResponse

router = APIRouter(prefix="/internal", tags=["travel"])


@router.post("/travel/plan", response_model=TravelPlanResponse)
# Spring Boot의 정규화 요청을 LangGraph에 전달하고 계획을 반환한다.
def create_travel_plan(payload: TravelPlanRequest) -> TravelPlanResponse:
    state = travel_graph.invoke({"request": payload.model_dump()})
    return TravelPlanResponse(
        status=state["status"],
        slots=state["slots"],
        selected_agents=state["selected_agents"],
        execution_plan=[AgentStep(**step) for step in state["execution_plan"]],
        retry_count=state["retry_count"],
        messages=state["messages"],
        missing_fields=state.get("missing_fields", []),
        clarification_questions=state.get("clarification_questions", []),
        conflicts=state.get("conflicts", []),
    )
