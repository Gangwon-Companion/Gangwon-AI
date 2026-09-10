from __future__ import annotations

from operator import add
from typing import Annotated, Literal, TypedDict


AgentName = Literal[
    "destination", "restaurant", "lodging", "itinerary",
    "validator", "validation", "response",
]


class TravelRequest(TypedDict, total=False):
    message: str
    region: str | None
    travel_days: int | None
    nights: int | None
    pet_allowed: bool | None
    pet_size: str | None
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
    matched_keywords: list[str]
    matched_preference_details: list[dict[str, object]]
    region_code: str | None
    region_match: bool | None
    opens_at: str | None
    closes_at: str | None
    pet_allowed: bool | None
    max_pet_size: str | None
    indoor_pet_allowed: bool | None
    wheelchair_accessible: bool | None
    source_ids: list[str]


class PreferenceProfile(TypedDict, total=False):
    keywords: list[str]
    soft: dict[str, float]


class LodgingCandidate(TypedDict, total=False):
    place_id: str
    name: str
    distance_km: float | None
    status: Literal["OK", "INSUFFICIENT_EVIDENCE"]
    missing_fields: list[str]
    latitude: float | None
    longitude: float | None
    opens_at: str | None
    closes_at: str | None
    address: str
    reason: str
    matched_conditions: list[str]
    matched_keywords: list[str]
    matched_preference_details: list[dict[str, object]]
    region_code: str | None
    region_match: bool | None
    pet_allowed: bool | None
    max_pet_size: str | None
    indoor_pet_allowed: bool | None
    wheelchair_accessible: bool | None
    source_ids: list[str]


class RestaurantCandidate(TypedDict, total=False):
    place_id: str
    name: str
    subtype: str | None
    distance_km: float | None
    cuisine: list[str]
    score: float
    status: Literal["OK", "INSUFFICIENT_EVIDENCE"]
    matched_conditions: list[str]
    matched_keywords: list[str]
    matched_preference_details: list[dict[str, object]]
    place_subtype: str | None
    region_code: str | None
    region_match: bool | None
    missing_fields: list[str]
    reason: str
    latitude: float | None
    longitude: float | None
    opens_at: str | None
    closes_at: str | None
    address: str
    pet_allowed: bool | None
    max_pet_size: str | None
    indoor_pet_allowed: bool | None
    wheelchair_accessible: bool | None
    source_ids: list[str]


class ScheduledVisit(TypedDict, total=False):
    slot: str
    day: int
    place_id: str
    name: str
    category: Literal["DESTINATION", "RESTAURANT", "LODGING"]
    subtype: str | None
    start_time: str
    end_time: str
    travel_minutes_from_previous: int
    latitude: float | None
    longitude: float | None
    source_ids: list[str]
    tags: list[str]
    address: str | None
    opens_at: str | None
    closes_at: str | None
    pet_allowed: bool | None
    max_pet_size: str | None
    indoor_pet_allowed: bool | None
    wheelchair_accessible: bool | None
    recommendation_reason: str
    matched_conditions: list[str]


class RetryAction(TypedDict):
    agent: AgentName
    slots: list[str]
    instruction: str


class SearchRelaxation(TypedDict, total=False):
    agent: AgentName
    domain: str
    slot: str
    retry_count: int
    original_query: str
    used_query: str
    original_regions: list[str]
    used_regions: list[str]
    strategy: str
    reason: str
    source: str
    failure_reasons: list[str]
    suggested_actions: list[str]


class SearchDiagnostic(TypedDict):
    agent: AgentName
    domain: str
    slot: str
    retry_count: int
    requested_limit: int
    returned_count: int
    unique_count: int
    shortage: int
    failure_reasons: list[str]
    under_matched_preferences: list[str]
    unmatched_query_terms: list[str]
    missing_evidence_fields: list[str]
    counts: dict[str, int]
    suggested_actions: list[str]


class ItinerarySlot(TypedDict, total=False):
    slot: str
    place_id: str
    name: str
    category: Literal["DESTINATION", "RESTAURANT", "LODGING"]
    subtype: str | None
    start_at: str
    end_at: str
    latitude: float | None
    longitude: float | None
    travel_minutes_from_previous: int
    pet_allowed: bool | None
    max_pet_size: str | None
    indoor_pet_allowed: bool | None
    wheelchair_accessible: bool | None
    opens_at: str | None
    closes_at: str | None
    source_ids: list[str]
    tags: list[str]
    address: str | None
    recommendation_reason: str
    matched_conditions: list[str]


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
    target_agent: AgentName
    target_preferences: list[str]


class QualityValidationResult(TypedDict):
    status: Literal["PASS", "REVISE"]
    score: int
    issues: list[QualityIssue]
    next_actions: list[ValidationAction]


class ResponseVisit(TypedDict, total=False):
    slot: str
    time: str
    place_id: str
    name: str
    category: str
    subtype: str | None
    address: str | None
    recommendation_reason: str
    operating_hours: str | None
    accessibility: dict[str, object]
    travel_minutes_from_previous: int
    unverified_fields: list[str]
    source_ids: list[str]


class ResponseDay(TypedDict):
    day: int
    date: str | None
    summary: str
    visits: list[ResponseVisit]


class FinalTravelResponse(TypedDict):
    response_status: Literal["READY", "PENDING", "FAILED"]
    title: str
    summary: str
    answer: str
    days: list[ResponseDay]
    accommodations: list[ResponseVisit]
    notices: list[str]
    quality_score: int | None
    source_ids: list[str]


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
    search_relaxations: Annotated[list[SearchRelaxation], add]
    search_diagnostics: Annotated[list[SearchDiagnostic], add]
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
    final_response: FinalTravelResponse
