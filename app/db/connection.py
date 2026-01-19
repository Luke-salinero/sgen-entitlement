import sqlite3
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()

DB_PATH = Path(settings.db_path)
SCHEMA_PATH = Path(__file__).resolve().parent / "db_schema.sql"


def _apply_schema(conn: sqlite3.Connection) -> None:
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)


def _subjects_has_api_key_column(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='subjects';"
    ).fetchone()
    if row is None:
        return False

    cols = [r[1] for r in conn.execute("PRAGMA table_info(subjects);").fetchall()]
    return "apiKey" in cols


def _rebuild_entitlements_schema_if_needed(conn: sqlite3.Connection) -> None:
    """
    If we detect an old subjects schema (no apiKey column),
    drop entitlements tables and reapply schema.sql.
    """
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='subjects';"
    ).fetchone()
    if row is not None and not _subjects_has_api_key_column(conn):
        conn.execute("DROP TABLE IF EXISTS subject_plan_limits;")
        conn.execute("DROP TABLE IF EXISTS subject_plan;")
        conn.execute("DROP TABLE IF EXISTS subjects;")
        conn.execute("DROP TABLE IF EXISTS plan_limits;")
        conn.execute("DROP TABLE IF EXISTS plans;")
        conn.commit()


def get_connection() -> sqlite3.Connection:
    """
    Creates and returns an SQLite connection and ensures schema.sql is applied.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    conn.execute(
        "PRAGMA foreign_keys = ON;"
        if settings.db_foreign_keys_on
        else "PRAGMA foreign_keys = OFF;"
    )
    conn.execute(f"PRAGMA busy_timeout = {settings.db_busy_timeout_ms};")

    _rebuild_entitlements_schema_if_needed(conn)

    _apply_schema(conn)
    conn.commit()

    return conn
