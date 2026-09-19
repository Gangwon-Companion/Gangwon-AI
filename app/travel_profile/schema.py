from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlaceType(str, Enum):
    ATTRACTION = "ATTRACTION"
    RESTAURANT = "RESTAURANT"
    LODGING = "LODGING"


class ActivityBase(StrictModel):
    place_type: PlaceType | None = None
    place_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)


class SearchActivity(StrictModel):
    keyword: str = Field(min_length=1, max_length=200)
    region: str | None = Field(default=None, min_length=1, max_length=100)
    searched_at: datetime


class VisitActivity(ActivityBase):
    category: str | None = Field(default=None, min_length=1, max_length=100)
    region: str | None = Field(default=None, min_length=1, max_length=100)
    visited_at: datetime


class SavedPlace(ActivityBase):
    region: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, min_length=1, max_length=100)


class SavedCourse(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    saved_at: datetime
    places: list[SavedPlace] = Field(default_factory=list)


class ReviewActivity(ActivityBase):
    rating: float = Field(ge=0, le=5)
    reviewed_at: datetime


class TravelProfileRequest(StrictModel):
    schema_version: str
    reference_time: datetime
    searches: list[SearchActivity]
    visits: list[VisitActivity]
    saved_courses: list[SavedCourse]
    reviews: list[ReviewActivity]

    @field_validator("reference_time")
    @classmethod
    def reference_time_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reference_time must include a timezone offset")
        return value

    @field_validator("searches", "visits", "saved_courses", "reviews")
    @classmethod
    def activity_times_must_have_timezone(cls, values: list[object]) -> list[object]:
        for value in values:
            for field_name in ("searched_at", "visited_at", "saved_at", "reviewed_at"):
                timestamp = getattr(value, field_name, None)
                if timestamp is not None and (timestamp.tzinfo is None or timestamp.utcoffset() is None):
                    raise ValueError(f"{field_name} must include a timezone offset")
        return values


class ProfileStatus(str, Enum):
    COMPLETED = "COMPLETED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TravelerType(str, Enum):
    CAPF = "CAPF"
    CAPH = "CAPH"
    CASF = "CASF"
    CASH = "CASH"
    CRPF = "CRPF"
    CRPH = "CRPH"
    CRSF = "CRSF"
    CRSH = "CRSH"
    NAPF = "NAPF"
    NAPH = "NAPH"
    NASF = "NASF"
    NASH = "NASH"
    NRPF = "NRPF"
    NRPH = "NRPH"
    NRSF = "NRSF"
    NRSH = "NRSH"


class AxisScores(StrictModel):
    space: dict[str, int]
    activity: dict[str, int]
    schedule: dict[str, int]
    place: dict[str, int]

    @field_validator("space")
    @classmethod
    def validate_space(cls, values: dict[str, int]) -> dict[str, int]:
        return cls._validate_axis(values, {"C", "N"})

    @field_validator("activity")
    @classmethod
    def validate_activity(cls, values: dict[str, int]) -> dict[str, int]:
        return cls._validate_axis(values, {"A", "R"})

    @field_validator("schedule")
    @classmethod
    def validate_schedule(cls, values: dict[str, int]) -> dict[str, int]:
        return cls._validate_axis(values, {"P", "S"})

    @field_validator("place")
    @classmethod
    def validate_place(cls, values: dict[str, int]) -> dict[str, int]:
        return cls._validate_axis(values, {"F", "H"})

    @staticmethod
    def _validate_axis(values: dict[str, int], keys: set[str]) -> dict[str, int]:
        if set(values) != keys or any(value < 0 or value > 100 for value in values.values()):
            raise ValueError("invalid travel type axis scores")
        if sum(values.values()) != 100:
            raise ValueError("axis scores must total 100")
        return values


class TravelProfileResponse(StrictModel):
    status: ProfileStatus
    traveler_type: TravelerType | None
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=5)
    evidences: list[str] = Field(default_factory=list, max_length=3)
    confidence: float | None = Field(default=None, ge=0, le=1)
    axis_scores: AxisScores | None = None
    analysis_version: str

    @field_validator("tags", mode="before")
    @classmethod
    def deduplicate_tags(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, values: list[str]) -> list[str]:
        if any(not (1 <= len(value) <= 30) for value in values):
            raise ValueError("each tag must contain 1 to 30 characters")
        return values

    @field_validator("evidences", mode="before")
    @classmethod
    def deduplicate_evidences(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @field_validator("evidences")
    @classmethod
    def validate_evidences(cls, values: list[str]) -> list[str]:
        if any(not (1 <= len(value) <= 200) for value in values):
            raise ValueError("each evidence must contain 1 to 200 characters")
        return values
