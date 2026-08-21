from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlaceDomain(str, Enum):
    DESTINATION = "DESTINATION"
    RESTAURANT = "RESTAURANT"
    LODGING = "LODGING"


class RegionCode(str, Enum):
    CHUNCHEON = "CHUNCHEON"
    WONJU = "WONJU"
    GANGNEUNG = "GANGNEUNG"
    DONGHAE = "DONGHAE"
    TAEBAEK = "TAEBAEK"
    SOKCHO = "SOKCHO"
    SAMCHEOK = "SAMCHEOK"
    HONGCHEON = "HONGCHEON"
    HOENGSEONG = "HOENGSEONG"
    YEONGWOL = "YEONGWOL"
    PYEONGCHANG = "PYEONGCHANG"
    JEONGSEON = "JEONGSEON"
    CHEORWON = "CHEORWON"
    HWACHEON = "HWACHEON"
    YANGGU = "YANGGU"
    INJE = "INJE"
    GOSEONG = "GOSEONG"
    YANGYANG = "YANGYANG"


class PetSize(str, Enum):
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"


class SearchStatus(str, Enum):
    OK = "OK"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class HardFilters(ContractModel):
    pet_allowed: bool | None = None
    pet_size: PetSize | None = None
    wheelchair_accessible: bool | None = None

    @model_validator(mode="after")
    def pet_size_requires_pet_travel(self) -> HardFilters:
        if self.pet_size is not None and self.pet_allowed is not True:
            raise ValueError("pet_size requires pet_allowed=true")
        return self


class GeoCenter(ContractModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class GeoConstraint(ContractModel):
    center: GeoCenter
    radius_km: float = Field(gt=0, le=200)


class SearchRequest(ContractModel):
    domain: PlaceDomain
    slot: str = Field(min_length=1, max_length=50)
    region_codes: list[RegionCode] = Field(default_factory=list, max_length=18)
    query_text: str = Field(default="", max_length=500)
    hard_filters: HardFilters = Field(default_factory=HardFilters)
    soft_preferences: dict[str, float] = Field(default_factory=dict)
    geo: GeoConstraint | None = None
    limit: int = Field(default=5, ge=1, le=100)

    @model_validator(mode="after")
    def validate_preferences_and_regions(self) -> SearchRequest:
        invalid_weights = [
            key for key, weight in self.soft_preferences.items() if not 0 <= weight <= 1
        ]
        if invalid_weights:
            raise ValueError("soft preference weights must be between 0 and 1")
        if len(set(self.region_codes)) != len(self.region_codes):
            raise ValueError("region_codes cannot contain duplicates")
        return self


class Location(ContractModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class Evidence(ContractModel):
    field: str = Field(min_length=1)
    value: Any
    source: str = Field(min_length=1)


class SearchCandidate(ContractModel):
    place_id: str = Field(min_length=1)
    domain: PlaceDomain
    name: str = Field(min_length=1)
    address: str | None = None
    location: Location | None = None
    distance_km: float | None = Field(default=None, ge=0)
    score: float = Field(ge=0)
    status: SearchStatus
    missing_fields: list[str] = Field(default_factory=list)
    matched_preferences: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def status_matches_missing_fields(self) -> SearchCandidate:
        if self.status == SearchStatus.OK and self.missing_fields:
            raise ValueError("OK candidates cannot have missing_fields")
        if self.status == SearchStatus.INSUFFICIENT_EVIDENCE and not self.missing_fields:
            raise ValueError("INSUFFICIENT_EVIDENCE requires missing_fields")
        return self


class SearchResponse(ContractModel):
    results: list[SearchCandidate] = Field(default_factory=list)
