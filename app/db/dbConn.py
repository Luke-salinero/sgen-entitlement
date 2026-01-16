from __future__ import annotations

import sqlite3
from typing import Generator

from app.core import get_settings

from .connection import get_connection
from .repo import PlanRepo


def get_db() -> Generator[sqlite3.Connection, None, None]:
    settings = get_settings()
    conn = get_connection(
        db_path=settings.db_path,
        foreign_keys_on=settings.db_foreign_keys_on,
        busy_timeout_ms=settings.db_busy_timeout_ms,
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_repo() -> Generator[PlanRepo, None, None]:
    for conn in get_db():
        yield PlanRepo(conn)
