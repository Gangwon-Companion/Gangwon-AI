from fastapi import APIRouter

from app.agents.itinerary import itinerary_node
from app.graph import travel_graph
from app.schemas.travel import (
    AgentStep,
    DestinationCandidate,
    LodgingCandidate,
    ItineraryPreviewRequest,
    ItineraryResult,
    NormalizedRequest,
    PreferenceProfile,
    RestaurantCandidate,
    RetryAction,
    ScheduledVisit,
    SearchRequest,
    TravelPlanRequest,
    TravelPlanResponse,
)

router = APIRouter(prefix="/internal", tags=["travel"])


@router.post(
    "/travel/itinerary/preview",
    response_model=ItineraryResult,
    summary="후보 기반 일정 최적화 미리보기",
    description="전문 Agent의 후보를 직접 입력해 Itinerary Optimizer 결과를 확인합니다.",
)
def preview_itinerary(payload: ItineraryPreviewRequest) -> ItineraryResult:
    state = {
        "slots": payload.slots,
        "preference_profile": payload.preference_profile.model_dump(),
        "destination_candidates": [item.model_dump() for item in payload.destination_candidates],
        "restaurant_candidates": [item.model_dump() for item in payload.restaurant_candidates],
        "lodging_candidates": [item.model_dump() for item in payload.lodging_candidates],
    }
    result = itinerary_node(state)  # type: ignore[arg-type]
    return ItineraryResult(
        itinerary_status=result["itinerary_status"],
        itinerary=[ScheduledVisit(**item) for item in result.get("itinerary", [])],
        itinerary_score=result.get("itinerary_score"),
        itinerary_alternatives=[
            [ScheduledVisit(**item) for item in plan]
            for plan in result.get("itinerary_alternatives", [])
        ],
        missing_slots=result.get("missing_slots", []),
        retry_actions=[RetryAction(**item) for item in result.get("retry_actions", [])],
    )


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
        destination_candidates=[
            DestinationCandidate(**c) for c in state.get("destination_candidates", [])
        ],
        destination_search_request=(
            SearchRequest(**vars(state["destination_search_request"]))
            if state.get("destination_search_request")
            else None
        ),
        lodging_candidates=[LodgingCandidate(**c) for c in state.get("lodging_candidates", [])],
        search_request=(
            SearchRequest(**vars(state["search_request"]))
            if state.get("search_request")
            else None
        ),
        restaurant_candidates=[
            RestaurantCandidate(**c) for c in state.get("restaurant_candidates", [])
        ],
        restaurant_search_request=(
            SearchRequest(**vars(state["restaurant_search_request"]))
            if state.get("restaurant_search_request")
            else None
        ),
        itinerary_status=state.get("itinerary_status"),
        itinerary=[ScheduledVisit(**item) for item in state.get("itinerary", [])],
        itinerary_score=state.get("itinerary_score"),
        itinerary_alternatives=[
            [ScheduledVisit(**item) for item in plan]
            for plan in state.get("itinerary_alternatives", [])
        ],
        missing_slots=state.get("missing_slots", []),
        retry_actions=[RetryAction(**item) for item in state.get("retry_actions", [])],
    )
