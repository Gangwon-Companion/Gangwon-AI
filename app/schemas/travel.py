from __future__ import annotations

from pydantic import BaseModel, Field
from app.search.models import SearchRequest


# 필수 정보가 없어도 요청은 받는다. 누락 판정과 재질문은 ConflictChecker가 담당하므로
# 여기서 422로 막으면 plan.md 0.3의 "추가 질문 반환" 흐름에 도달할 수 없다.
class TravelPlanRequest(BaseModel):
    message: str = Field(..., min_length=1, description="사용자 원본 요청")
    region: str | None = None
    travel_days: int | None = Field(default=None, ge=1, le=30)
    nights: int | None = Field(default=None, ge=0, le=29)
    pet_allowed: bool | None = Field(default=None, description="None은 미입력을 뜻한다")
    pet_size: str | None = None
    wheelchair_accessible: bool | None = None
    indoor_pet: bool | None = None
    max_price: int | None = Field(default=None, ge=0)
    preferences: list[str] = Field(default_factory=list)


# FormBinder까지 마친 요청을 그대로 돌려주는 응답 필드다. 재질문이 필요할 때
# 호출한 쪽이 이 값을 다음 요청에 그대로 실어 보내면 앞 턴에서 채운 항목이 유지된다.
# message는 담지 않는다. 다음 요청의 message는 사용자의 새 답변이어야 한다.
class NormalizedRequest(BaseModel):
    region: str | None = None
    travel_days: int | None = None
    nights: int | None = None
    pet_allowed: bool | None = None
    pet_size: str | None = None
    wheelchair_accessible: bool | None = None
    indoor_pet: bool | None = None
    max_price: int | None = Field(default=None, ge=0)
    preferences: list[str] = Field(default_factory=list)


class AgentStep(BaseModel):
    agent: str
    mode: str
    depends_on: list[str] = Field(default_factory=list)


class PreferenceProfile(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    soft: dict[str, float] = Field(default_factory=dict)
    activity_requested: bool = False


class DestinationCandidate(BaseModel):
    destination_id: int
    title: str
    addr1: str
    map_x: float
    map_y: float
    theme_code: str
    source_types: list[str] = Field(default_factory=list)
    score: float
    reason: str
    matched_conditions: list[str] = Field(default_factory=list)
    opens_at: str | None = None
    closes_at: str | None = None
    pet_allowed: bool | None = None
    max_pet_size: str | None = None
    indoor_pet_allowed: bool | None = None
    wheelchair_accessible: bool | None = None
    source_ids: list[str] = Field(default_factory=list)


class LodgingCandidate(BaseModel):
    place_id: str
    name: str
    distance_km: float | None = None
    status: str
    missing_fields: list[str] = Field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    opens_at: str | None = None
    closes_at: str | None = None
    address: str | None = None
    reason: str = ""
    matched_conditions: list[str] = Field(default_factory=list)
    pet_allowed: bool | None = None
    max_pet_size: str | None = None
    indoor_pet_allowed: bool | None = None
    wheelchair_accessible: bool | None = None
    source_ids: list[str] = Field(default_factory=list)


class RestaurantCandidate(BaseModel):
    place_id: str
    name: str
    distance_km: float | None = None
    cuisine: list[str] = Field(default_factory=list)
    score: float
    status: str
    matched_conditions: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    reason: str
    latitude: float | None = None
    longitude: float | None = None
    opens_at: str | None = None
    closes_at: str | None = None
    address: str | None = None
    pet_allowed: bool | None = None
    max_pet_size: str | None = None
    indoor_pet_allowed: bool | None = None
    wheelchair_accessible: bool | None = None
    source_ids: list[str] = Field(default_factory=list)


class ScheduledVisit(BaseModel):
    slot: str
    day: int
    place_id: str
    name: str
    category: str
    start_time: str
    end_time: str
    travel_minutes_from_previous: int = 0
    latitude: float | None = None
    longitude: float | None = None
    source_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    address: str | None = None
    opens_at: str | None = None
    closes_at: str | None = None
    pet_allowed: bool | None = None
    max_pet_size: str | None = None
    indoor_pet_allowed: bool | None = None
    wheelchair_accessible: bool | None = None
    recommendation_reason: str = ""
    matched_conditions: list[str] = Field(default_factory=list)


class ValidationAction(BaseModel):
    agent: str
    slots: list[str] = Field(default_factory=list)
    instruction: str


class RetryAction(BaseModel):
    agent: str
    slots: list[str] = Field(default_factory=list)
    instruction: str


class HardViolation(BaseModel):
    code: str
    slots: list[str] = Field(default_factory=list)
    place_id: str = ""
    reason: str
    source_ids: list[str] = Field(default_factory=list)


class HardValidationResult(BaseModel):
    status: str
    violations: list[HardViolation] = Field(default_factory=list)
    next_actions: list[ValidationAction] = Field(default_factory=list)


class QualityIssue(BaseModel):
    type: str
    severity: str
    slots: list[str] = Field(default_factory=list)
    reason: str


class QualityValidationResult(BaseModel):
    status: str
    score: int = Field(ge=0, le=100)
    issues: list[QualityIssue] = Field(default_factory=list)
    next_actions: list[ValidationAction] = Field(default_factory=list)


class ItinerarySlot(BaseModel):
    slot: str
    place_id: str
    name: str
    category: str
    start_at: str
    end_at: str
    latitude: float | None = None
    longitude: float | None = None
    travel_minutes_from_previous: int = Field(default=0, ge=0)
    pet_allowed: bool | None = None
    max_pet_size: str | None = None
    indoor_pet_allowed: bool | None = None
    wheelchair_accessible: bool | None = None
    opens_at: str | None = None
    closes_at: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    address: str | None = None
    recommendation_reason: str = ""
    matched_conditions: list[str] = Field(default_factory=list)


class ValidationRequest(BaseModel):
    request: TravelPlanRequest
    preference_profile: PreferenceProfile = Field(default_factory=PreferenceProfile)
    itinerary: list[ItinerarySlot] = Field(min_length=1)


class ValidationResponse(BaseModel):
    hard_validation: HardValidationResult
    quality_validation: QualityValidationResult | None = None


class ResponseAccessibility(BaseModel):
    wheelchair_accessible: bool | None = None
    pet_allowed: bool | None = None
    indoor_pet_allowed: bool | None = None
    max_pet_size: str | None = None


class ResponseVisit(BaseModel):
    slot: str
    time: str
    place_id: str
    name: str
    category: str
    address: str | None = None
    recommendation_reason: str
    operating_hours: str | None = None
    accessibility: ResponseAccessibility
    travel_minutes_from_previous: int = 0
    unverified_fields: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)


class ResponseDay(BaseModel):
    day: int
    date: str | None = None
    summary: str
    visits: list[ResponseVisit] = Field(default_factory=list)


class FinalTravelResponse(BaseModel):
    response_status: str
    title: str
    summary: str
    answer: str
    days: list[ResponseDay] = Field(default_factory=list)
    notices: list[str] = Field(default_factory=list)
    quality_score: int | None = None
    source_ids: list[str] = Field(default_factory=list)


class ResponsePreviewRequest(BaseModel):
    request: TravelPlanRequest
    preference_profile: PreferenceProfile = Field(default_factory=PreferenceProfile)
    itinerary_status: str = "READY"
    itinerary: list[ItinerarySlot] = Field(min_length=1)
    hard_validation: HardValidationResult
    quality_validation: QualityValidationResult


class ItineraryPreviewRequest(BaseModel):
    slots: list[str] = Field(min_length=1)
    preference_profile: PreferenceProfile = Field(default_factory=PreferenceProfile)
    destination_candidates: list[DestinationCandidate] = Field(default_factory=list)
    restaurant_candidates: list[RestaurantCandidate] = Field(default_factory=list)
    lodging_candidates: list[LodgingCandidate] = Field(default_factory=list)


class ItineraryResult(BaseModel):
    itinerary_status: str
    itinerary: list[ScheduledVisit] = Field(default_factory=list)
    itinerary_score: float | None = None
    itinerary_alternatives: list[list[ScheduledVisit]] = Field(default_factory=list)
    missing_slots: list[str] = Field(default_factory=list)
    retry_actions: list[RetryAction] = Field(default_factory=list)

class TravelPlanResponse(BaseModel):
    status: str
    input_complete: bool = False
    request: NormalizedRequest = Field(default_factory=NormalizedRequest)
    slots: list[str] = Field(default_factory=list)
    selected_agents: list[str] = Field(default_factory=list)
    execution_plan: list[AgentStep] = Field(default_factory=list)
    preference_profile: PreferenceProfile = Field(default_factory=PreferenceProfile)
    retry_count: int = 0
    messages: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    destination_candidates: list[DestinationCandidate] = Field(default_factory=list)
    destination_search_request: SearchRequest | None = None
    lodging_candidates: list[LodgingCandidate] = Field(default_factory=list)
    search_request: SearchRequest | None = None
    restaurant_candidates: list[RestaurantCandidate] = Field(default_factory=list)
    restaurant_search_request: SearchRequest | None = None
    hard_validation: HardValidationResult | None = None
    quality_validation: QualityValidationResult | None = None
    itinerary_status: str | None = None
    itinerary: list[ScheduledVisit] = Field(default_factory=list)
    itinerary_score: float | None = None
    itinerary_alternatives: list[list[ScheduledVisit]] = Field(default_factory=list)
    missing_slots: list[str] = Field(default_factory=list)
    retry_actions: list[RetryAction] = Field(default_factory=list)
