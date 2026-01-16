from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db import EntitlementsRepo, get_db

router = APIRouter()

DbConn = Annotated[sqlite3.Connection, Depends(get_db)]


class SubjectSyncRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    api_key: str = Field(..., min_length=1)
    account_name: str = Field(..., min_length=1)
    default_tier: str = Field("free", min_length=1)
    status: str = Field("active", min_length=1)


class SubjectSyncResponse(BaseModel):
    user_id: str
    default_tier: str
    subject_upserted: bool
    default_plan_ensured: bool


@router.post("/internal/subjects/sync", response_model=SubjectSyncResponse)
def auth_sync(req: SubjectSyncRequest, conn: DbConn):
    repo = EntitlementsRepo(conn)

    # Upsert subject + rotate api_key
    try:
        repo.upsert_subject(
            user_id=req.user_id,
            api_key=req.api_key,
            account_name=req.account_name,
            status=req.status,
        )
    except sqlite3.IntegrityError as err:
        raise HTTPException(
            status_code=409, detail=f"Subject upsert failed: {err}"
        ) from err

    try:
        repo.ensure_subject_default_plan(
            user_id=req.user_id, default_tier=req.default_tier
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    except sqlite3.IntegrityError as err:
        raise HTTPException(
            status_code=409, detail=f"Default plan ensure failed: {err}"
        ) from err

    return SubjectSyncResponse(
        user_id=req.user_id,
        default_tier=req.default_tier,
        subject_upserted=True,
        default_plan_ensured=True,
    )
