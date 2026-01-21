# app/api/v1.py
from __future__ import annotations

import sqlite3
from typing import Iterator
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core import (
    AuthenticationError,
    EntitlementService,
    InvalidAuthenticationError,
    MissingAuthenticationError,
    PlanInactiveError,
    SubjectInactiveError,
    SubjectNotFoundError,
    authenticate_request,
    get_settings,
)
from app.db import PlanRepo, get_connection

router = APIRouter(prefix="/v1", tags=["v1"])


def get_conn() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def _request_id_from_headers(request: Request) -> str:
    """
    Prefer the gateway-provided request id for traceability.
    If missing, generate one.
    """
    return request.headers.get("x-request-id") or str(uuid4())


def _get_entitlement_service(conn=Depends(get_conn)) -> EntitlementService:
    """
    Establishes connection to the Repository
    """
    repo = PlanRepo(conn)
    return EntitlementService(repo)


@router.get("/whoami")
async def whoami(request: Request, response: Response) -> dict:
    """
    Debug endpoint: proves authentication plumbing works.
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
        # Catch-all auth error → 401
        raise HTTPException(status_code=401, detail=exc.message) from exc

    return {
        "subject_id": identity.subject_id,
        "account_name": identity.account_name,
        "provider": identity.provider,
    }


@router.get("/entitlements")
async def entitlements(
    request: Request,
    response: Response,
    svc: EntitlementService = Depends(_get_entitlement_service),
) -> dict:
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
    try:
        effective = svc.get_entitlements(identity.raw_claims)
    except SubjectNotFoundError as exc:
        # Raise error for now. We'll have an edpoint connection create the
        # user from a link
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except SubjectInactiveError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PlanInactiveError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        detail = "Entitlements service unavailable"
        if get_settings().debug:
            detail = f"{detail}: {type(exc).__name__}: {exc}"
        raise HTTPException(status_code=503, detail=detail) from exc

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
