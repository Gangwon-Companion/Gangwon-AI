"""Final-answer grounding checks for the natural-language response renderer.

This is deliberately conservative: a failed check uses the deterministic
response assembled from validated itinerary data. It does not replace the
Hard Validator; it protects the prose rendering step after validation.
"""
from __future__ import annotations

import json
import re
from typing import Any


# Place IDs are data, not a domain-specific enum. Keep the detector generic so
# new domains do not require code changes (e.g. HOTEL:7, ACTIVITY:42).
_PLACE_ID = re.compile(r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]*:\d+(?![A-Za-z0-9_])")
_NUMBER = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[,.]\d+)?%?(?![A-Za-z])")
_TIME = re.compile(r"(?<!\d)(?:[01]?\d|2[0-3]):[0-5]\d(?!\d)")


def _walk(value: Any):
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)
    else:
        yield value


def _normal_number(value: str) -> str:
    return value.replace(",", "").rstrip("%")


def validate_final_answer(answer: str, *, days: list[dict[str, Any]],
                         notices: list[str],
                         accommodations: list[dict[str, Any]] | None = None) -> tuple[bool, str]:
    """Return whether an LLM answer only contains grounded identifiers/values."""
    if not isinstance(answer, str) or not answer.strip():
        return False, "empty_answer"

    accommodation_visits = accommodations or []
    visits = [visit for day in days for visit in day.get("visits", [])]
    visits.extend(accommodation_visits)
    source = {
        "days": days,
        "accommodations": accommodation_visits,
        "notices": notices,
    }
    allowed_ids = {
        str(value) for visit in visits for value in
        (visit.get("place_id"), *visit.get("source_ids", [])) if value
    }
    mentioned_ids = set(_PLACE_ID.findall(answer))
    unknown_ids = mentioned_ids - allowed_ids
    if unknown_ids:
        return False, "unknown_place_id"

    structured_text = _PLACE_ID.sub("", json.dumps(source, ensure_ascii=False))
    allowed_numbers = {
        _normal_number(value) for value in _NUMBER.findall(structured_text)
    }
    # Dates and times are represented in the structured input; compare their
    # visible numeric fragments as well as explicit HH:MM values.
    allowed_times = set(_TIME.findall(json.dumps(source, ensure_ascii=False)))
    for value in _TIME.findall(answer):
        if value not in allowed_times:
            return False, "unknown_time"

    text_without_ids = _PLACE_ID.sub("", answer)
    for value in _NUMBER.findall(text_without_ids):
        if _normal_number(value) not in allowed_numbers:
            return False, "unknown_number"
    return True, "ok"


def validate_claims(claims: Any, *, days: list[dict[str, Any]],
                    accommodations: list[dict[str, Any]] | None = None) -> tuple[bool, str]:
    """Validate structured LLM claims against the itinerary evidence surface."""
    if not isinstance(claims, list):
        return False, "claims_not_list"

    visits = [visit for day in days for visit in day.get("visits", [])]
    visits.extend(accommodations or [])
    by_id = {str(visit.get("place_id")): visit for visit in visits if visit.get("place_id")}
    for claim in claims:
        if not isinstance(claim, dict):
            return False, "claim_not_object"
        text = claim.get("text")
        place_id = claim.get("place_id")
        fields = claim.get("evidence_fields", [])
        evidence = claim.get("evidence", [])
        confidence = claim.get("confidence")
        if not isinstance(text, str) or not text.strip():
            return False, "claim_text_missing"
        if not isinstance(place_id, str) or place_id not in by_id:
            return False, "claim_unknown_place_id"
        if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
            return False, "claim_evidence_fields_invalid"
        if not isinstance(evidence, list):
            return False, "claim_evidence_invalid"
        if confidence not in {"SUPPORTED", "UNCERTAIN"}:
            return False, "claim_confidence_invalid"
        if confidence == "SUPPORTED":
            visit = by_id[place_id]
            unverified = set(visit.get("unverified_fields", []))
            allowed = _grounded_fields(visit)
            if any(field not in allowed or field in unverified for field in fields):
                return False, "claim_unsupported_evidence"
            if not _evidence_values_match(evidence, fields, visit):
                return False, "claim_evidence_value_mismatch"
    return True, "ok"


def _grounded_fields(visit: dict[str, Any]) -> set[str]:
    fields = {"place_id", "name", "address", "source_ids", "recommendation_reason"}
    if visit.get("operating_hours"):
        fields.add("operating_hours")
    if visit.get("time"):
        fields.add("time")
    accessibility = visit.get("accessibility") or {}
    fields.update(key for key, value in accessibility.items() if value is not None)
    return fields


def _evidence_values_match(evidence: list[Any], fields: list[str], visit: dict[str, Any]) -> bool:
    if not fields:
        return True
    by_field = {
        item.get("field"): item.get("value")
        for item in evidence
        if isinstance(item, dict) and isinstance(item.get("field"), str)
    }
    if any(field not in by_field for field in fields):
        return False
    for field in fields:
        expected = _field_value(visit, field)
        actual = by_field[field]
        if field == "source_ids":
            if actual not in (visit.get("source_ids") or []):
                return False
        elif actual != expected:
            return False
    return True


def _field_value(visit: dict[str, Any], field: str) -> Any:
    if field in {"wheelchair_accessible", "pet_allowed", "indoor_pet_allowed", "max_pet_size"}:
        return (visit.get("accessibility") or {}).get(field)
    return visit.get(field)
