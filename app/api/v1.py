# app/api/v1.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.auth import (
    AuthenticationError,
    InvalidAuthenticationError,
    MissingAuthenticationError,
    authenticate_request,
)

router = APIRouter(prefix="/v1", tags=["v1"])


@router.get("/whoami")
async def whoami(request: Request) -> dict:
    """
    Debug endpoint: proves authentication plumbing works.
    Gateway (or you) calls this with auth headers.
    """
    try:
        identity = authenticate_request(request.headers)
    except MissingAuthenticationError as exc:
        raise HTTPException(status_code=401, detail=exc.message) from exc
    except InvalidAuthenticationError as exc:
        raise HTTPException(status_code=401, detail=exc.message) from exc
    except AuthenticationError as exc:
        # Catch-all auth error → 401
        raise HTTPException(status_code=401, detail=exc.message) from exc

    return {
        "subject_id": identity.subject_id,
        "account_name": identity.account_name,
        "provider": identity.provider,
    }
