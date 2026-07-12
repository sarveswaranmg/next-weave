"""
Security & Privacy: Tenant Isolation, API Key Auth, RBAC Scaffold

Tenant isolation is enforced throughout NeuroWeave by scoping every query
to `user_id` — visible in every service built across Days 1-9, not a Day
10 addition. This module adds the pieces that weren't already implicit:
an API key gate for the runtime API surface, and a minimal role/
permission model RBAC can build on. Encryption at rest/in transit, SOC 2/
GDPR/HIPAA compliance, and multi-region disaster recovery are
operational/infrastructure concerns documented in
`DAY10_RUNTIME_PLATFORM.md` rather than code — see that file's "Security
& Privacy" section for what's implemented vs. guidance.
"""
import logging
from enum import Enum
from typing import Optional

from fastapi import Header, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)


class Role(str, Enum):
    """Minimal RBAC role model - extend as real auth is added."""
    ADMIN = "admin"
    DEVELOPER = "developer"
    READONLY = "readonly"


ROLE_PERMISSIONS = {
    Role.ADMIN: {"read", "write", "delete", "manage_plugins", "run_benchmarks"},
    Role.DEVELOPER: {"read", "write", "run_benchmarks"},
    Role.READONLY: {"read"},
}


def has_permission(role: Role, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


async def verify_api_key(x_api_key: Optional[str] = Header(default=None)) -> bool:
    """
    FastAPI dependency gating the runtime API surface. No-op (always
    allows) when `settings.runtime_api_key` is unset, so local development
    and the existing test suite don't need a key configured — set
    RUNTIME_API_KEY in production to require one.
    """
    if not settings.runtime_api_key:
        return True
    if x_api_key != settings.runtime_api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    return True
