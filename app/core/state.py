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
    region: str
    travel_days: int
    nights: int
    pet_allowed: bool
    pet_size: str
    wheelchair_accessible: bool
    preferences: list[str]


class TravelState(TypedDict, total=False):
    request: TravelRequest
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
