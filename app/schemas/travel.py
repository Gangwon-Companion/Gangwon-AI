from __future__ import annotations

from pydantic import BaseModel, Field


class TravelPlanRequest(BaseModel):
    message: str = Field(..., min_length=1, description="Spring Boot에서 정규화한 원본 요청")
    region: str = Field(..., min_length=1)
    travel_days: int = Field(..., ge=1, le=30)
    nights: int | None = Field(default=None, ge=0, le=29)
    pet_allowed: bool
    pet_size: str | None = None
    wheelchair_accessible: bool = False
    preferences: list[str] = Field(default_factory=list)


class AgentStep(BaseModel):
    agent: str
    mode: str
    depends_on: list[str] = Field(default_factory=list)


class TravelPlanResponse(BaseModel):
    status: str
    slots: list[str] = Field(default_factory=list)
    selected_agents: list[str] = Field(default_factory=list)
    execution_plan: list[AgentStep] = Field(default_factory=list)
    retry_count: int = 0
    messages: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
