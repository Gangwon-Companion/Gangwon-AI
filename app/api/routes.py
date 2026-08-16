from fastapi import APIRouter

from app.graph import travel_graph
from app.schemas.travel import (
    AgentStep,
    LodgingCandidate,
    NormalizedRequest,
    PreferenceProfile,
    SearchRequest,
    TravelPlanRequest,
    TravelPlanResponse,
)

router = APIRouter(prefix="/internal", tags=["travel"])


@router.post("/travel/plan", response_model=TravelPlanResponse)
# 사용자 요청을 LangGraph에 전달하고 계획 또는 추가 질문을 반환한다.
# 필수 정보가 없으면 input_complete=false와 clarification_questions를 돌려준다.
# 이때 응답의 request를 다음 요청에 그대로 실어 보내면 앞 턴에서 채운 항목이 유지되므로,
# 호출한 쪽은 사용자의 새 답변만 message에 담으면 된다.
def create_travel_plan(payload: TravelPlanRequest) -> TravelPlanResponse:
    # 생략된 Form 필드는 Binder가 자연어로 보완할 수 있도록 보존한다.
    # 특히 wheelchair_accessible의 스키마 기본값 False를 그대로 넘기면
    # 사용자가 자연어로 "휠체어"라고 입력해도 미입력과 구분할 수 없다.
    state = travel_graph.invoke({"request": payload.model_dump(exclude_unset=True)})
    normalized = {k: v for k, v in state.get("request", {}).items() if k != "message"}
    return TravelPlanResponse(
        status=state["status"],
        input_complete=state.get("input_complete", False),
        request=NormalizedRequest(**normalized),
        slots=state.get("slots", []),
        selected_agents=state.get("selected_agents", []),
        execution_plan=[AgentStep(**step) for step in state.get("execution_plan", [])],
        preference_profile=PreferenceProfile(**state.get("preference_profile", {})),
        retry_count=state.get("retry_count", 0),
        messages=state.get("messages", []),
        missing_fields=state.get("missing_fields", []),
        clarification_questions=state.get("clarification_questions", []),
        conflicts=state.get("conflicts", []),
        lodging_candidates=[LodgingCandidate(**c) for c in state.get("lodging_candidates", [])],
        search_request=(
            SearchRequest(**vars(state["search_request"]))
            if state.get("search_request")
            else None
        ),
    )
