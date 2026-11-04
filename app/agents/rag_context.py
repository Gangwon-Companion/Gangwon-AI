"""Build explicit retrieval context for grounded final-answer generation."""
from __future__ import annotations

from typing import Any


def _verified_value(visit: dict[str, Any], field: str) -> Any:
    """Return a value only when the itinerary explicitly marks it verified."""
    unverified = set(visit.get("unverified_fields") or [])
    if field in unverified or field.removeprefix("accessibility.") in unverified:
        return None
    return visit.get(field)


def _visit_document(visit: dict[str, Any]) -> dict[str, Any]:
    accessibility = {
        key: value
        for key, value in (visit.get("accessibility") or {}).items()
        if value is not None
        and key not in set(visit.get("unverified_fields") or [])
    }
    return {
        "document_id": str(visit.get("place_id") or ""),
        "content": {
            field: value
            for field, value in {
                "place_id": visit.get("place_id"),
                "name": visit.get("name"),
                "category": visit.get("category"),
                "subtype": visit.get("subtype"),
                "address": _verified_value(visit, "address"),
                "time": _verified_value(visit, "time"),
                "operating_hours": _verified_value(visit, "operating_hours"),
                "accessibility": accessibility,
            }.items()
            if value is not None and value != {}
        },
        "evidence": {
            "source_ids": list(dict.fromkeys(visit.get("source_ids") or [])),
        },
    }


def build_rag_context(
    *,
    days: list[dict[str, Any]],
    accommodations: list[dict[str, Any]] | None = None,
    notices: list[str] | None = None,
) -> dict[str, Any]:
    """Convert the validated itinerary into a small, JSON-safe evidence surface."""
    documents: list[dict[str, Any]] = []
    seen: set[str] = set()
    visits = [visit for day in days for visit in day.get("visits", [])]
    visits.extend(accommodations or [])
    for visit in visits:
        document = _visit_document(visit)
        document_id = document["document_id"]
        if not document_id or document_id in seen:
            continue
        seen.add(document_id)
        documents.append(document)
    return {"documents": documents, "notices": list(dict.fromkeys(notices or []))}
