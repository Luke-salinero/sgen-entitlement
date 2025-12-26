# app/api/v1.py
from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, Response

from app.core import (
    AuthenticationError,
    EntitlementService,
    InactivePlanError,
    InvalidAuthenticationError,
    MissingAuthenticationError,
    SubjectInactiveError,
    SubjectNotFoundError,
    authenticate_request,
)
from app.db import PlanRepo, get_connection

router = APIRouter(prefix="/v1", tags=["v1"])


def _request_id_from_headers(request: Request) -> str:
    """
    Prefer the gateway-provided request id for traceability.
    If missing, generate one.
    """
    return request.headers.get("x-request-id") or str(uuid4())


def _get_entitlement_service() -> EntitlementService:
    """
    Establishes connection to the Repository
    """

    # LOOK INTO ADDING Depends
    conn = get_connection()
    repo = PlanRepo(conn)
    return EntitlementService(repo)


@router.get("/whoami")
async def whoami(request: Request) -> dict:
    """
    Debug endpoint: proves authentication plumbing works.
    """
    request_id = _request_id_from_headers(request)
    request.headers["X-Request-Id"] = request_id
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


@router.get("/entitlements")
async def entitlements(request: Request, response: Response) -> dict:
    """
    Returns effective entitlements for the authenticated subject.
    The gateway uses this to enforce limits/flags (tier, allow_live, max_n, etc.).
    """
    request_id = _request_id_from_headers(request)
    response.headers["X-Request-Id"] = request_id

    try:
        identity = authenticate_request(request.headers)
    except MissingAuthenticationError as exc:
        raise HTTPException(status_code=401, detail=exc.message) from exc
    except InvalidAuthenticationError as exc:
        raise HTTPException(status_code=401, detail=exc.message) from exc
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=exc.message) from exc

    # Get Entitlement Service class, call our Repo functions to get entitlements
    # connected to our subject id.
    svc = _get_entitlement_service()
    try:
        effective = svc.get_entitlements({"userID": identity.subject_id})
    except SubjectNotFoundError as exc:
        # Raising error here for now, but should we create a new user
        # if one isnt found, or will we make another endpoint that listens
        # for when a new email is registered?
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except SubjectInactiveError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except InactivePlanError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        # DB down / unexpected repo failure → service unavailable
        raise HTTPException(
            status_code=503, detail="Entitlements service unavailable"
        ) from exc

    return {
        "subject_id": effective.userID,
        "account_name": effective.accountName,
        "tier": effective.tier,
        "allow_live": effective.allow_live,
        "limits": {
            "max_n": effective.max_n,
            "max_k": effective.max_k,
            "existential_only": effective.existential_only,
            "rate_limit": effective.rate_limit,
            "rate_window": effective.rate_window,
        },
    }
