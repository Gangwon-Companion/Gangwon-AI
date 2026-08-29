from __future__ import annotations

import json
import logging
import os
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.core.state import ResponseDay


logger = logging.getLogger(__name__)


class ResponseLLMClient(Protocol):
    def create_answer(self, *, model: str, instructions: str, input_text: str) -> str:
        ...


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

    def create_answer(self, *, model: str, instructions: str, input_text: str) -> str:
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")

        body = {
            "model": model,
            "instructions": instructions,
            "input": input_text,
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
            raise RuntimeError(
                f"OpenAI response generation failed: HTTP {exc.code} {detail}"
            ) from exc
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"OpenAI response generation failed: {exc}") from exc

        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()
        text = _extract_text_from_output(payload)
        if text:
            return text
        raise RuntimeError("OpenAI response did not include output text.")


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
    client: ResponseLLMClient | None = None,
) -> str:
    if not llm_enabled():
        return fallback_answer

    model = os.getenv("GANGWON_RESPONSE_LLM_MODEL", "gpt-4.1")
    llm_client = client or OpenAIResponsesClient()
    try:
        answer = llm_client.create_answer(
            model=model,
            instructions=_instructions(),
            input_text=_input_text(
                title=title,
                summary=summary,
                days=days,
                notices=notices,
                quality_score=quality_score,
                source_ids=source_ids,
            ),
        )
    except Exception as exc:
        logger.warning(
            "Response LLM rendering failed; using fallback answer. model=%s error=%s: %s",
            model,
            exc.__class__.__name__,
            exc,
        )
        return fallback_answer
    return answer or fallback_answer


def _instructions() -> str:
    return (
        "너는 검증 완료된 강원 여행 일정의 최종 답변 문장만 작성한다. "
        "입력 JSON에 있는 장소, 시간, 주소, 운영시간, 접근성, 반려동물 정책, "
        "미확인 정보만 사용한다. 장소를 추가하거나 삭제하지 말고, "
        "일정을 바꾸지 말고, null 또는 미확인 값을 가능하다고 추정하지 마라. "
        "한국어로 자연스럽고 읽기 쉽게 작성하되, 내부 출처 ID나 근거 ID는 절대 출력하지 마라."
    )


def _input_text(
    *,
    title: str,
    summary: str,
    days: list[ResponseDay],
    notices: list[str],
    quality_score: int | None,
    source_ids: list[str],
) -> str:
    payload = {
        "title": title,
        "summary": summary,
        "days": days,
        "notices": notices,
        "quality_score": quality_score,
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
