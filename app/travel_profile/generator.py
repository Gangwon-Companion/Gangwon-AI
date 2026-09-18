from __future__ import annotations

import json
import logging
import os
import re
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.response_llm import OpenAIResponsesClient, ResponseLLMClient
from app.travel_profile.prompt import profile_input, profile_instructions
from app.travel_profile.schema import AxisScores, TravelProfileRequest, TravelerType


logger = logging.getLogger(__name__)
KOREAN_PATTERN = re.compile(r"[가-힣]")


class GeneratedProfileCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=500)
    tags: list[str] = Field(min_length=1, max_length=5)
    evidences: list[str] = Field(min_length=1, max_length=3)
    confidence: float | None = Field(default=None, ge=0, le=1)

    @field_validator("title", "description")
    @classmethod
    def korean_text(cls, value: str) -> str:
        value = value.strip()
        if not KOREAN_PATTERN.search(value):
            raise ValueError("user-facing text must be Korean")
        return value

    @field_validator("tags", "evidences", mode="before")
    @classmethod
    def deduplicate_lists(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @field_validator("tags")
    @classmethod
    def valid_tags(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not (1 <= len(value) <= 30) or not KOREAN_PATTERN.search(value) for value in cleaned):
            raise ValueError("tags must be Korean and contain 1 to 30 characters")
        return cleaned

    @field_validator("evidences")
    @classmethod
    def clean_evidences(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values]


class ProfileCopyGenerator(Protocol):
    def generate(
        self,
        *,
        payload: TravelProfileRequest,
        traveler_type: TravelerType,
        axis_scores: AxisScores,
        evidence_candidates: list[str],
        fallback: GeneratedProfileCopy,
    ) -> GeneratedProfileCopy:
        ...


class LLMProfileCopyGenerator:
    def __init__(self, client: ResponseLLMClient | None = None) -> None:
        timeout = float(os.getenv("GANGWON_TRAVEL_PROFILE_LLM_TIMEOUT_SECONDS", "8"))
        self._client = client or OpenAIResponsesClient(timeout_seconds=timeout)

    def generate(
        self,
        *,
        payload: TravelProfileRequest,
        traveler_type: TravelerType,
        axis_scores: AxisScores,
        evidence_candidates: list[str],
        fallback: GeneratedProfileCopy,
    ) -> GeneratedProfileCopy:
        if not profile_llm_enabled():
            return fallback
        model = os.getenv("GANGWON_TRAVEL_PROFILE_LLM_MODEL", "gpt-4.1-mini")
        try:
            raw = self._client.create_answer(
                model=model,
                instructions=profile_instructions(),
                input_text=profile_input(
                    traveler_type=traveler_type,
                    axis_scores=axis_scores,
                    activity_context=_activity_context(payload),
                    evidence_candidates=evidence_candidates,
                ),
            )
            generated = GeneratedProfileCopy.model_validate(json.loads(_json_text(raw)))
            if any(item not in evidence_candidates for item in generated.evidences):
                raise ValueError("LLM returned evidence outside evidence_candidates")
            return generated
        except Exception as exc:
            logger.warning(
                "Travel profile LLM generation failed; using grounded fallback. model=%s error=%s: %s",
                model,
                exc.__class__.__name__,
                exc,
            )
            return fallback


def profile_llm_enabled() -> bool:
    configured = os.getenv("GANGWON_TRAVEL_PROFILE_LLM_ENABLED")
    if configured is not None:
        return configured.lower() in {"1", "true", "yes", "on"}
    return bool(os.getenv("OPENAI_API_KEY"))


def _activity_context(payload: TravelProfileRequest) -> dict[str, object]:
    # Limit prompt size and expose only fields already allowed by the request contract.
    return {
        "searches": [
            {"keyword": item.keyword, "region": item.region}
            for item in payload.searches[:20]
        ],
        "visits": [
            {"name": item.name, "category": item.category, "region": item.region}
            for item in payload.visits[:20]
        ],
        "saved_courses": [
            {"name": course.name, "places": [place.name for place in course.places[:20]]}
            for course in payload.saved_courses[:10]
        ],
        "reviews": [
            {"name": item.name, "rating": item.rating}
            for item in payload.reviews[:20]
        ],
    }


def _json_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM output did not contain a JSON object")
    return text[start : end + 1]
