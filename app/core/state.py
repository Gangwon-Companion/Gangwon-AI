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
    wheelchair_accessible: bool
    preferences: list[str]


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


class TravelState(TypedDict, total=False):
    request: TravelRequest
    preference_profile: PreferenceProfile
    input_complete: bool
    missing_fields: list[str]
    clarification_questions: list[str]
    conflicts: list[str]
    slots: list[str]
    selected_agents: list[AgentName]
    execution_plan: list[dict[str, object]]
    retry_count: int
    status: Literal["needs_clarification", "planned", "running", "completed", "failed"]
    errors: Annotated[list[str], add]
    messages: Annotated[list[str], add]
    lodging_candidates: list[LodgingCandidate]
