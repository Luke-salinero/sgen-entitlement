"""
Public exports for the core package.
"""

# Auth exports
from .auth import (
    AuthenticationError,
    Identity,
    InvalidAuthenticationError,
    MissingAuthenticationError,
    authenticate_request,
)
from .config import (
    get_settings,
)

# Entitlements exports
from .entitlementService import (
    EffectiveEntitlements,
    EntitlementsError,
    EntitlementService,
    PlanInactiveError,
    SubjectInactiveError,
    SubjectNotFoundError,
)

__all__ = [
    # Auth
    "Identity",
    "AuthenticationError",
    "MissingAuthenticationError",
    "InvalidAuthenticationError",
    "authenticate_request",
    # Entitlements
    "EffectiveEntitlements",
    "EntitlementService",
    "EntitlementsError",
    "SubjectNotFoundError",
    "SubjectInactiveError",
    "PlanInactiveError",
    # Config,
    "get_settings",
]
