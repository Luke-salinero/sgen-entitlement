# app/main.py
from fastapi import FastAPI

from app.api.v1 import router as v1_router
from app.db.sync.auth_sync import router as sync_router

app = FastAPI(title="Entitlements Service")

app.include_router(v1_router)
app.include_router(sync_router)
