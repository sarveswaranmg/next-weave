"""
Security & Privacy: Multi-Tenant API Key Auth, RBAC Enforcement

`Tenant` is the SaaS auth boundary (see `neurowave_engine.db.models.Tenant`) - a single
tenant manages many `User` rows (end-users of the tenant's own
application). Every request authenticates against the `api_keys` table to
exactly one `ApiKey` row, which resolves to exactly one `tenant_id` - any
`user_id` referenced in a request body/query param must then be checked
against that `tenant_id` (see `neurowave_engine.services.tenancy`) before being
trusted. This replaces the old model where a single shared
`RUNTIME_API_KEY` secret gated the whole deployment and a client-supplied
`user_id` was trusted with no ownership check at all (letting any caller
holding that one key read or delete *any* tenant's data by
guessing/enumerating UUIDs).

Encryption at rest for stored provider credentials lives in
`neurowave_engine/core/crypto.py`. Encryption at rest for the database itself, SOC 2/
GDPR/HIPAA compliance, and multi-region disaster recovery remain
operational/infrastructure concerns outside application code.
"""
import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from neurowave_engine.db.database import get_db
from neurowave_engine.db.models import ApiKey, Role

logger = logging.getLogger(__name__)

ROLE_PERMISSIONS = {
    Role.ADMIN: {"read", "write", "delete", "manage_plugins", "run_benchmarks", "manage_keys"},
    Role.DEVELOPER: {"read", "write", "run_benchmarks"},
    Role.READONLY: {"read"},
}


def has_permission(role: Role, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


@dataclass
class AuthContext:
    """
    Resolved identity for one authenticated request. `tenant_id` is the
    SaaS billing/auth boundary - a single tenant manages many `User` rows,
    so this does NOT resolve to one `user_id`. Any `user_id` referenced in
    a request body/query param must be checked against this `tenant_id`
    via `neurowave_engine.services.tenancy` before being trusted.
    """
    tenant_id: UUID
    role: Role
    api_key_id: UUID


_KEY_PREFIX_LEN = 12


def _hash_secret(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


def generate_api_key(env: str = "live") -> Tuple[str, str, str]:
    """
    Generate a new API key. Returns (plaintext, key_prefix, hashed_secret).
    The plaintext is shown to the caller exactly once, at creation time —
    only `key_prefix` (for fast lookup) and `hashed_secret` (sha256) are
    ever persisted.
    """
    raw_key = f"nw_{env}_{secrets.token_urlsafe(32)}"
    key_prefix = raw_key[:_KEY_PREFIX_LEN]
    return raw_key, key_prefix, _hash_secret(raw_key)


async def verify_api_key(
    x_api_key: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> AuthContext:
    """
    FastAPI dependency authenticating one request against the `api_keys`
    table. There is no no-op/unset fallback — every request must present a
    valid, unrevoked key. A deployment with no keys yet must bootstrap one
    first (see `scripts/bootstrap_tenant.py`).
    """
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    key_prefix = x_api_key[:_KEY_PREFIX_LEN]
    hashed = _hash_secret(x_api_key)
    candidates = db.query(ApiKey).filter(ApiKey.key_prefix == key_prefix).all()
    match = next((k for k in candidates if hmac.compare_digest(k.hashed_secret, hashed)), None)

    if not match or match.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")

    match.last_used_at = datetime.utcnow()
    db.commit()

    return AuthContext(tenant_id=match.tenant_id, role=Role(match.role), api_key_id=match.id)


def require_permission(permission: str):
    """
    Dependency factory: `Depends(require_permission("delete"))` gates a
    route on the resolved `AuthContext`'s role actually having that
    permission, on top of just presenting a valid key.
    """
    async def _check(auth: AuthContext = Depends(verify_api_key)) -> AuthContext:
        if not has_permission(auth.role, permission):
            raise HTTPException(
                status_code=403,
                detail=f"API key role '{auth.role.value}' lacks the '{permission}' permission",
            )
        return auth

    return _check
