from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping, Optional

from jose import jwt
from jose.exceptions import JWTError

from .config import get_settings


@dataclass(frozen=True)
class Identity:
    """
    Identity from an authorization provider
    """

    subject_id: str
    account_name: Optional[str]
    provider: str
    raw_claims: Mapping[str, object]


class AuthenticationError(Exception):
    """Base class for authentication failures."""

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.code = code


class MissingAuthenticationError(AuthenticationError):
    def __init__(self, message: str = "Authentication required"):
        super().__init__(message, code="auth_missing")


class InvalidAuthenticationError(AuthenticationError):
    def __init__(self, message: str = "Invalid authentication credentials"):
        super().__init__(message, code="auth_invalid")


@lru_cache(maxsize=1)
def _fetch_jwks(jwks_url: str) -> dict[str, Any]:
    """
    Fetch Keycloak JWKS and cache it to avoid pulling on every request.
    If you rotate realm keys, restart the service (or remove caching later).
    """
    with urllib.request.urlopen(jwks_url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _select_jwk_for_token(token: str, jwks: dict[str, Any]) -> dict[str, Any]:
    header = jwt.get_unverified_header(token)
    kid = header.get("kid")
    if not kid:
        raise InvalidAuthenticationError("JWT header missing 'kid'")

    keys = jwks.get("keys") or []
    for k in keys:
        if k.get("kid") == kid:
            return k

    raise InvalidAuthenticationError(f"No matching JWK found for kid={kid}")


def _authenticate_bearer(auth_header: str) -> Identity:
    """
    Authenticate using a standard Authorization: Bearer <token> header.
    """
    if not auth_header.startswith("Bearer "):
        raise InvalidAuthenticationError("Unsupported authorization scheme")

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise InvalidAuthenticationError("Empty bearer token")

    try:
        settings = get_settings()

        # If a JWKS URL is configured, verify like Keycloak expects (RS256 via JWKS).
        # Otherwise, fall back to the old "shared secret / static key" behavior for dev.
        jwks_url = getattr(settings, "jwt_jwks_url", None)

        options: dict[str, Any] = {}
        if settings.jwt_leeway_seconds:
            options["leeway"] = settings.jwt_leeway_seconds

        if jwks_url:
            jwks = _fetch_jwks(jwks_url)
            jwk_key = _select_jwk_for_token(token, jwks)

            claims = jwt.decode(
                token,
                key=jwk_key,
                algorithms=list(settings.jwt_algorithms),
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
                options=options or None,
            )
        else:
            # Old path (HS256 or manually-provided key)
            claims = jwt.decode(
                token,
                key=settings.jwt_public_key,
                algorithms=list(settings.jwt_algorithms),
                audience=settings.jwt_audience,
                issuer=settings.jwt_issuer,
                options=options or None,
            )

    except JWTError as err:
        raise InvalidAuthenticationError("Invalid bearer token") from err

    subject_id = claims.get("sub")
    if not subject_id:
        raise InvalidAuthenticationError("Missing subject in token")

    return Identity(
        subject_id=str(subject_id),
        account_name=claims.get("email"),
        provider="bearer",
        raw_claims=claims,
    )


def authenticate_request(headers: Mapping[str, str]) -> Identity:
    """
    Determine the authentication from request headers
    Return an Identity.
    """
    auth_header = headers.get("Authorization")
    if auth_header:
        return _authenticate_bearer(auth_header)

    raise MissingAuthenticationError("No supported authentication headers found")
