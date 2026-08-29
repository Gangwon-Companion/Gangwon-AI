import os

from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

from app.api.routes import router
from app.agents.response_llm import llm_enabled

app = FastAPI(title="Gangwon Travel Planner", version="0.1.0")
app.include_router(router)


@app.get("/health", tags=["health"])
# 서버 상태를 확인하는 health check API다.
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "response_llm_enabled": llm_enabled(),
        "openai_key_configured": bool(os.getenv("OPENAI_API_KEY")),
        "response_llm_model": os.getenv("GANGWON_RESPONSE_LLM_MODEL", "gpt-4.1"),
    }
