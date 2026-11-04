from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.state import ResponseDay, ResponseVisit
from app.agents.answer_grounding import validate_claims, validate_final_answer


logger = logging.getLogger(__name__)


class ResponseLLMClient(Protocol):
    def create_answer(
        self, *, model: str, instructions: str, input_text: str,
        response_schema: dict[str, object] | None = None,
    ) -> str:
        ...


class ResponseLLMError(RuntimeError):
    """An API-level response failure that is distinct from grounding failure."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        message = reason if not detail else f"{reason}: {detail}"
        super().__init__(message)


class OpenAIResponsesClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com").rstrip("/")
        self._timeout_seconds = timeout_seconds

    def create_answer(
        self, *, model: str, instructions: str, input_text: str,
        response_schema: dict[str, object] | None = None,
    ) -> str:
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        body = {
            "model": model,
            "instructions": instructions,
            "input": input_text,
        }
        if response_schema is not None:
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "grounded_travel_answer",
                    "strict": True,
                    "schema": response_schema,
                }
            }
        request = Request(
            f"{self._base_url}/v1/responses",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = _http_error_detail(exc)
            raise ResponseLLMError("response_api_error", f"HTTP {exc.code} {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise ResponseLLMError("response_transport_error", str(exc)) from exc

        status = payload.get("status")
        if status == "incomplete" or payload.get("incomplete_details"):
            raise ResponseLLMError("response_incomplete", str(payload.get("incomplete_details") or status))
        if _contains_refusal(payload):
            raise ResponseLLMError("response_refusal")

        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        text = _extract_text_from_output(payload)
        if text:
            return text
        raise ResponseLLMError("response_no_output")


def llm_enabled() -> bool:
    configured = os.getenv("GANGWON_RESPONSE_LLM_ENABLED")
    if configured is not None:
        return configured.lower() in {"1", "true", "yes", "on"}
    return bool(os.getenv("OPENAI_API_KEY"))


def render_answer_with_llm(
    *,
    title: str,
    summary: str,
    days: list[ResponseDay],
    notices: list[str],
    quality_score: int | None,
    source_ids: list[str],
    fallback_answer: str,
    accommodations: list[ResponseVisit] | None = None,
    rag_context: dict[str, object] | None = None,
    client: ResponseLLMClient | None = None,
) -> str:
    if not llm_enabled():
        return fallback_answer

    model = os.getenv("GANGWON_RESPONSE_LLM_MODEL", "gpt-4.1")
    llm_client = client or OpenAIResponsesClient()
    try:
        place_ids = _place_ids(days, accommodations or [])
        response_schema = _answer_schema(dict.fromkeys(place_ids))
        answer = llm_client.create_answer(
            model=model,
            instructions=_instructions() + "\nReturn JSON matching the supplied schema. "
                         "Create one claim per place: each claim has exactly one place_id string, never an array or null. "
                         "Use only confidence SUPPORTED or UNCERTAIN. "
                         "Use evidence items with field and value; use the exact field path and value from the input.",
            input_text=_input_text(
                title=title,
                summary=summary,
                days=days,
                accommodations=accommodations or [],
                notices=notices,
                quality_score=quality_score,
                source_ids=source_ids,
                rag_context=rag_context or {},
            ),
            response_schema=response_schema,
        )
    except Exception as exc:
        logger.warning(
            "Response LLM rendering failed; using fallback answer. model=%s error=%s: %s",
            model,
            exc.__class__.__name__,
            exc,
        )
        return fallback_answer
    if not answer:
        return fallback_answer
    structured = _parse_structured_answer(answer)
    if structured is not None:
        grounded_claims, claim_reason = validate_claims(
            structured.get("claims"),
            days=days,
            accommodations=accommodations or [],
        )
        if not grounded_claims:
            logger.warning("Response LLM claims failed grounding; using fallback. reason=%s", claim_reason)
            return fallback_answer
        answer = structured.get("answer", "")
    grounded, reason = validate_final_answer(
        answer,
        days=days,
        notices=notices,
        accommodations=accommodations or [],
    )
    if not grounded:
        logger.warning("Response LLM answer failed grounding; using fallback. reason=%s", reason)
        return fallback_answer
    return answer


def _instructions() -> str:
    return (
        "너는 검증 완료된 강원 여행 일정의 최종 답변 문장만 작성한다. "
        "입력 JSON에 있는 장소, 시간, 주소, 운영시간, 접근성, 반려동물 정책, "
        "미확인 정보만 사용한다. 장소를 추가하거나 삭제하지 말고, "
        "일정을 바꾸지 말고, null 또는 미확인 값을 가능하다고 추정하지 마라. "
        "한국어로 자연스럽고 읽기 쉽게 작성하되, 내부 출처 ID나 근거 ID는 절대 출력하지 마라."
    ) + (
        " The retrieved_context is the only factual source. "
        "Only repeat fields that are present and non-null in retrieved_context. "
        "Do not mention or paraphrase omitted fields, unverified fields, ratings, distances, facilities, or reasons. "
        "If a fact is absent, omit the sentence entirely instead of saying or guessing it. "
        "Do not invent or infer facts outside it. "
        "The answer must be a concise itinerary summary, not a general travel guide."
    )


def _input_text(
    *,
    title: str,
    summary: str,
    days: list[ResponseDay],
    accommodations: list[ResponseVisit],
    notices: list[str],
    quality_score: int | None,
    source_ids: list[str],
    rag_context: dict[str, object],
) -> str:
    safe_documents = {
        str(document.get("document_id")): document.get("content", {})
        for document in (rag_context.get("documents", []) if isinstance(rag_context, dict) else [])
        if isinstance(document, dict) and document.get("document_id")
    }

    def safe_visit(visit: ResponseVisit) -> dict[str, Any]:
        place_id = str(visit.get("place_id") or "")
        content = safe_documents.get(place_id)
        if not isinstance(content, dict):
            return {"place_id": place_id, "name": visit.get("name")}
        # Give the model the reduced evidence surface used by RAG. This keeps
        # unverified fields and null placeholders out of the generation prompt.
        return dict(content)

    payload = {
        "title": title,
        "summary": summary,
        "days": [
            {
                "day": day.get("day"),
                "date": day.get("date"),
                "summary": day.get("summary"),
                "visits": [safe_visit(visit) for visit in day.get("visits", [])],
            }
            for day in days
        ],
        "accommodations": [safe_visit(visit) for visit in accommodations],
        "notices": notices,
        "quality_score": quality_score,
        "source_ids": source_ids,
        "retrieved_context": rag_context,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _extract_text_from_output(payload: dict[str, object]) -> str:
    chunks: list[str] = []
    output = payload.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunk.strip() for chunk in chunks if chunk.strip())


def _parse_structured_answer(answer: str) -> dict[str, object] | None:
    try:
        payload = json.loads(answer)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "answer" not in payload or "claims" not in payload:
        return None
    return payload


def _answer_schema(place_ids: dict[str, None]) -> dict[str, object]:
    claim_schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "text": {"type": "string"},
            "place_id": {"type": "string", "enum": list(place_ids)},
            "evidence_fields": {"type": "array", "items": {"type": "string"}},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "field": {"type": "string"},
                        "value": {"anyOf": [{"type": "string"}, {"type": "number"}, {"type": "boolean"}, {"type": "null"}]},
                    },
                    "required": ["field", "value"],
                },
            },
            "confidence": {"type": "string", "enum": ["SUPPORTED", "UNCERTAIN"]},
        },
        "required": ["text", "place_id", "evidence_fields", "evidence", "confidence"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "answer": {"type": "string"},
            "claims": {"type": "array", "items": claim_schema},
            "uncertainties": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["answer", "claims", "uncertainties"],
    }


def _place_ids(days: list[ResponseDay] | list[dict[str, object]], accommodations: list[ResponseVisit] | list[dict[str, object]]) -> list[str]:
    result: list[str] = []
    for day in days:
        visits = day.get("visits", []) if isinstance(day, dict) else getattr(day, "visits", [])
        for visit in visits:
            place_id = visit.get("place_id") if isinstance(visit, dict) else getattr(visit, "place_id", None)
            if place_id:
                result.append(str(place_id))
    for visit in accommodations:
        place_id = visit.get("place_id") if isinstance(visit, dict) else getattr(visit, "place_id", None)
        if place_id:
            result.append(str(place_id))
    return list(dict.fromkeys(result))


def _contains_refusal(payload: dict[str, object]) -> bool:
    output = payload.get("output")
    if not isinstance(output, list):
        return False
    return any(
        isinstance(part, dict) and part.get("type") == "refusal"
        for item in output if isinstance(item, dict)
        for part in (item.get("content") or []) if isinstance(item.get("content"), list)
    )


def _http_error_detail(exc: HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8")
    except Exception:
        return exc.reason
    if not body:
        return exc.reason
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body[:500]
    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        error_type = error.get("type")
        if message and error_type:
            return f"{error_type}: {message}"
        if message:
            return str(message)
    return body[:500]
