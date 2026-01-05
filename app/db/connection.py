import sqlite3
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = settings.db_path
# DB_PATH = BASE_DIR / "data" / "entitlements.db"


def get_connection() -> sqlite3.Connection:
    """
    Creates and returns an SQLite connection
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # SQlite objects created in a thread can only be used in that same thread
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)

    conn.execute(
        "PRAGMA foreign_keys = ON;"
        if settings.db_foreign_keys_on
        else "PRAGMA foreign_keys = OFF;"
    )
    conn.execute(f"PRAGMA busy_timeout = {settings.db_busy_timeout_ms};")

    return conn
