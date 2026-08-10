from __future__ import annotations

from pydantic import BaseModel, Field


# 필수 정보가 없어도 요청은 받는다. 누락 판정과 재질문은 ConflictChecker가 담당하므로
# 여기서 422로 막으면 plan.md 0.3의 "추가 질문 반환" 흐름에 도달할 수 없다.
class TravelPlanRequest(BaseModel):
    message: str = Field(..., min_length=1, description="사용자 원본 요청")
    region: str | None = None
    travel_days: int | None = Field(default=None, ge=1, le=30)
    nights: int | None = Field(default=None, ge=0, le=29)
    pet_allowed: bool | None = Field(default=None, description="None은 미입력을 뜻한다")
    pet_size: str | None = None
    wheelchair_accessible: bool = False
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
    wheelchair_accessible: bool = False
    preferences: list[str] = Field(default_factory=list)


class AgentStep(BaseModel):
    agent: str
    mode: str
    depends_on: list[str] = Field(default_factory=list)


class PreferenceProfile(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    soft: dict[str, float] = Field(default_factory=dict)
    activity_requested: bool = False


class LodgingCandidate(BaseModel):
    place_id: str
    name: str
    distance_km: float | None = None
    status: str
    missing_fields: list[str] = Field(default_factory=list)


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
    lodging_candidates: list[LodgingCandidate] = Field(default_factory=list)
