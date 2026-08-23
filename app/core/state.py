from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict


AgentName = Literal[
    "destination",
    "restaurant",
    "lodging",
    "activity",
    "itinerary",
    "validator",
    "validation",
    "response",
]


class TravelRequest(TypedDict, total=False):
    message: str
    region: str | None
    travel_days: int | None
    nights: int | None
    # None은 아직 입력받지 못한 상태이며, 반려동물 미동반(False)과 구분한다.
    pet_allowed: bool | None
    pet_size: str | None
    # None은 미입력, False는 무장애 조건 없음으로 구분한다.
    wheelchair_accessible: bool | None
    indoor_pet: bool | None
    max_price: int | None
    preferences: list[str]


SourceType = Literal["KOREAN", "PET", "ACCESSIBILITY"]


class DestinationCandidate(TypedDict, total=False):
    destination_id: int
    title: str
    addr1: str
    map_x: float
    map_y: float
    theme_code: str
    source_types: list[SourceType]
    score: float
    reason: str
    matched_conditions: list[str]


# PreferenceExtractor가 만든 파생 데이터로, 원본 요청(request)과 분리해 보관한다.
# soft는 plan.md 6장 SearchRequest의 softPreferences로 그대로 전달한다.
class PreferenceProfile(TypedDict, total=False):
    keywords: list[str]
    soft: dict[str, float]
    activity_requested: bool


class LodgingCandidate(TypedDict, total=False):
    place_id: str
    name: str
    distance_km: float | None
    status: Literal["OK", "INSUFFICIENT_EVIDENCE"]
    missing_fields: list[str]
    latitude: float
    longitude: float
    opens_at: str | None
    closes_at: str | None


class RestaurantCandidate(TypedDict, total=False):
    place_id: str
    name: str
    distance_km: float | None
    cuisine: list[str]
    score: float
    status: Literal["OK", "INSUFFICIENT_EVIDENCE"]
    matched_conditions: list[str]
    missing_fields: list[str]
    reason: str
    latitude: float
    longitude: float
    opens_at: str | None
    closes_at: str | None


class ScheduledVisit(TypedDict, total=False):
    slot: str
    day: int
    place_id: str
    name: str
    category: Literal["DESTINATION", "RESTAURANT", "LODGING", "ACTIVITY"]
    start_time: str
    end_time: str
    travel_minutes_from_previous: int
    latitude: float | None
    longitude: float | None
    source_ids: list[str]
    tags: list[str]


class RetryAction(TypedDict):
    agent: AgentName
    slots: list[str]
    instruction: str


class ItinerarySlot(TypedDict, total=False):
    slot: str
    place_id: str
    name: str
    category: Literal["DESTINATION", "RESTAURANT", "LODGING", "ACTIVITY"]
    start_at: str
    end_at: str
    latitude: float
    longitude: float
    travel_minutes_from_previous: int
    pet_allowed: bool | None
    max_pet_size: str | None
    indoor_pet_allowed: bool | None
    wheelchair_accessible: bool | None
    opens_at: str | None
    closes_at: str | None
    source_ids: list[str]
    tags: list[str]


class ValidationAction(TypedDict, total=False):
    agent: AgentName
    slots: list[str]
    instruction: str


class HardViolation(TypedDict, total=False):
    code: str
    slots: list[str]
    place_id: str
    reason: str
    source_ids: list[str]


class HardValidationResult(TypedDict):
    status: Literal["VALID", "INVALID"]
    violations: list[HardViolation]
    next_actions: list[ValidationAction]


class QualityIssue(TypedDict, total=False):
    type: str
    severity: Literal["MINOR", "MAJOR"]
    slots: list[str]
    reason: str


class QualityValidationResult(TypedDict):
    status: Literal["PASS", "REVISE"]
    score: int
    issues: list[QualityIssue]
    next_actions: list[ValidationAction]


class TravelState(TypedDict, total=False):
    request: TravelRequest
    preference_profile: PreferenceProfile
    input_complete: bool
    missing_fields: list[str]
    clarification_questions: list[str]
    conflicts: list[str]
    destination_candidates: list[DestinationCandidate]
    destination_search_request: object
    slots: list[str]
    selected_agents: list[AgentName]
    completed_agents: Annotated[list[AgentName], add]
    candidates_ready: bool
    execution_plan: list[dict[str, object]]
    retry_count: int
    retry_agents: list[AgentName]
    status: Literal["needs_clarification", "planned", "running", "completed", "failed"]
    errors: Annotated[list[str], add]
    messages: Annotated[list[str], add]
    lodging_candidates: list[LodgingCandidate]
    search_request: object
    restaurant_candidates: list[RestaurantCandidate]
    restaurant_search_request: object
    itinerary: list[ItinerarySlot | ScheduledVisit]
    hard_validation: HardValidationResult
    quality_validation: QualityValidationResult
    itinerary_status: Literal["READY", "NEEDS_CANDIDATES"]
    itinerary_score: float
    itinerary_alternatives: list[list[ScheduledVisit]]
    missing_slots: list[str]
    retry_actions: list[ValidationAction | RetryAction]
