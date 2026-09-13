from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.requests import Request
from starlette.responses import Response

from app.travel_profile.analyzer import TravelProfileAnalyzer
from app.travel_profile.auth import verify_internal_api_key
from app.travel_profile.schema import TravelProfileRequest, TravelProfileResponse


class BadRequestValidationRoute(APIRoute):
    """Return the profile contract's 400 instead of FastAPI's default 422."""

    def get_route_handler(self):  # type: ignore[no-untyped-def]
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as exc:
                from fastapi.exception_handlers import request_validation_exception_handler

                response = await request_validation_exception_handler(request, exc)
                response.status_code = 400
                return response

        return handler


router = APIRouter(
    prefix="/internal/travel/profile",
    tags=["travel-profile"],
    route_class=BadRequestValidationRoute,
)


@router.post(
    "/analyze",
    response_model=TravelProfileResponse,
    dependencies=[Depends(verify_internal_api_key)],
)
def analyze_travel_profile(payload: TravelProfileRequest) -> TravelProfileResponse:
    if payload.schema_version != "1.0":
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="unsupported schema_version")
    return TravelProfileAnalyzer().analyze(payload)
