import os

from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

from app.api.routes import router
from app.agents.response_llm import llm_enabled
from app.travel_profile.routes import router as travel_profile_router
from app.travel_profile.generator import profile_llm_enabled

app = FastAPI(title="Gangwon Travel Planner", version="0.1.0")
app.include_router(router)
app.include_router(travel_profile_router)


@app.get("/health", tags=["health"])
# 서버 상태를 확인하는 health check API다.
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "response_llm_enabled": llm_enabled(),
        "openai_key_configured": bool(os.getenv("OPENAI_API_KEY")),
        "response_llm_model": os.getenv("GANGWON_RESPONSE_LLM_MODEL", "gpt-4.1"),
        "travel_profile_llm_enabled": profile_llm_enabled(),
        "travel_profile_llm_model": os.getenv(
            "GANGWON_TRAVEL_PROFILE_LLM_MODEL", "gpt-4.1-mini"
        ),
    }
