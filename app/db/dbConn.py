from __future__ import annotations

import sqlite3
from typing import Generator

from .connection import get_connection
from .repo import PlanRepo


def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
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
