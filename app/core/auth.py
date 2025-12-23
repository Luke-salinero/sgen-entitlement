from dataclasses import dataclass
from typing import Mapping, Optional

# Maybe we can use python-jose to import jwt
# claims = jwt.decode(
#    token,
#    key=public_key,
#    algorithms=["RS256"],
#    audience="your-audience",
#    issuer="https://your.cloudflare.access/"
# )


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

    claims = "REPLACE WITH REAL DECODING OF JWT"  # _decode_jwt_without_verification(
    #  token
    # )  ##Replace with from jose import jwt?

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
