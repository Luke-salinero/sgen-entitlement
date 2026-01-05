from dataclasses import dataclass
from typing import Mapping, Optional

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


def _authenticate_bearer(auth_header: str) -> Identity:
    """
    Authenticate using a standard Authorization: Bearer <token> header.
    """
    if not auth_header.startswith("Bearer "):
        raise InvalidAuthenticationError("Unsupported authorization scheme")

    token = auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise InvalidAuthenticationError("Empty bearer token")

    # CHANGE ONCE WE KNOW HOW JWT IS FORMATTED
    try:
        settings = get_settings()

        # Change to RS256. Using HS256 for dev
        claims = jwt.decode(
            token,
            key=settings.jwt_public_key,
            algorithms=list(settings.jwt_algorithms),
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options=(
                {"leeway": settings.jwt_leeway_seconds}
                if settings.jwt_leeway_seconds
                else None
            ),
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
