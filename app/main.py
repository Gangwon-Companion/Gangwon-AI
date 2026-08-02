from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="Gangwon Travel Planner", version="0.1.0")
app.include_router(router)


@app.get("/health", tags=["health"])
# 서버 상태를 확인하는 health check API다.
def health() -> dict[str, str]:
    return {"status": "ok"}
