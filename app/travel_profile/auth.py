from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException, status


def verify_internal_api_key(
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-API-Key"),
) -> None:
    expected = os.getenv("INTERNAL_API_KEY")
    if not expected:
        return
    if x_internal_api_key is None or not hmac.compare_digest(x_internal_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid internal API key",
        )
