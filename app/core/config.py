# app/core/config.py
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# can import dotenv from loadenv
# so we can grab from the .env file
# BSD-2-Clause license


def _env(name: str, default: str | None = None) -> str:
    val = os.getenv(name, default)
    if val is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


@dataclass(frozen=True)
class Settings:
    # ---- App/service ----
    env: str = os.getenv("ENV", "dev")
    debug: bool = os.getenv("DEBUG", "0") == "1"
    service_name: str = os.getenv("SERVICE_NAME", "entitlements-service")
    request_id_header: str = os.getenv("REQUEST_ID_HEADER", "X-Request-Id")

    # ---- JWT verification ----
    jwt_issuer: str = _env("JWT_ISSUER", "http://127.0.0.1:8081/realms/sgen-test")
    jwt_audience: str = _env("JWT_AUDIENCE", "account")
    jwt_algorithms: tuple[str, ...] = tuple(
        os.getenv("JWT_ALGORITHMS", "RS256").split(",")
    )
    jwt_jwks_url: str = _env(
        "JWT_JWKS_URL",
        "https://sgen-cape.bigsigma.tech/realms/sgen-test/protocol/openid-connect/certs",
    )

    # Public key for RS256 verification.
    # Public Key = Secret Key in HS256
    jwt_public_key: str = _env("JWT_PUBLIC_KEY", "public_key")

    # Optional: small clock skew leeway (seconds) for exp/nbf checks
    jwt_leeway_seconds: int = int(os.getenv("JWT_LEEWAY_SECONDS", "0"))
    database_url = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/entitlements"

    # ---- Database (SQLite) ----
    # Default: <repo_root>/app/data/entitlements.db (matches your current pattern)
    base_dir: Path = Path(__file__).resolve().parent.parent
    db_path: Path = Path(
        os.getenv("DB_PATH", str(base_dir / "data" / "entitlements.db"))
    )
    db_busy_timeout_ms: int = int(os.getenv("DB_BUSY_TIMEOUT_MS", "5000"))
    db_foreign_keys_on: bool = os.getenv("DB_FOREIGN_KEYS_ON", "1") == "1"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Cached settings object. Call get_settings() wherever you need config.
    """
    return Settings()
