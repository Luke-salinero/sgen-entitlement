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

# Entitlements exports
from .entitlements.types import (
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
]
