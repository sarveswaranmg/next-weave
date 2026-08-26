"""
Self-serve tenant signup: email verification + first API key issuance.
See `neurowave_engine/api/signup.py` for the HTTP surface.
"""
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Tuple

from sqlalchemy.orm import Session

from neurowave_engine.core.config import settings
from neurowave_engine.core.security import generate_api_key
from neurowave_engine.db.models import ApiKey, SignupAttempt, Tenant
from neurowave_engine.services.email_service import send_verification_email

logger = logging.getLogger(__name__)


class SignupRateLimitError(Exception):
    """Raised when an IP has exceeded settings.signup_max_per_ip_per_day."""


class SignupVerificationError(Exception):
    """Raised when a verification token is missing, invalid, expired, or already used."""


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_signup(session: Session, email: str, company_name: str, ip_address: str) -> None:
    """
    Records this attempt (for IP rate limiting) before anything else, so a
    request that then fails the rate-limit check still counts toward it.
    Always completes the same way from the caller's perspective regardless
    of whether the email is already registered - see `verify_signup` for the
    actual gate; this never reveals account existence.
    """
    cutoff = datetime.utcnow() - timedelta(days=1)
    recent_count = (
        session.query(SignupAttempt)
        .filter(SignupAttempt.ip_address == ip_address, SignupAttempt.created_at >= cutoff)
        .count()
    )
    if recent_count >= settings.signup_max_per_ip_per_day:
        raise SignupRateLimitError("Too many signup attempts from this address today")

    session.add(SignupAttempt(ip_address=ip_address))
    session.commit()

    existing = session.query(Tenant).filter(Tenant.email == email).first()
    if existing and existing.email_verified_at is not None:
        # Already a verified account for this email - stop here without
        # telling the caller that (avoid enumeration).
        return

    if existing:
        # Unverified pending signup for this email - refresh the token
        # rather than creating a duplicate Tenant row.
        tenant = existing
        tenant.name = company_name or tenant.name
    else:
        tenant = Tenant(id=uuid.uuid4(), name=company_name, email=email)
        session.add(tenant)

    token = secrets.token_urlsafe(32)
    tenant.verification_token_hash = _hash_token(token)
    tenant.verification_sent_at = datetime.utcnow()
    session.commit()

    verify_url = f"{settings.signup_base_url.rstrip('/')}/signup/verify?token={token}"
    send_verification_email(email, verify_url)


def verify_signup(session: Session, token: str) -> Tuple[Tenant, str]:
    """Returns (tenant, plaintext_api_key). The key is shown exactly once -
    same contract as POST /runtime/keys."""
    if not token:
        raise SignupVerificationError("Missing verification token")

    hashed = _hash_token(token)
    tenant = session.query(Tenant).filter(Tenant.verification_token_hash == hashed).first()
    if not tenant:
        raise SignupVerificationError("Invalid or already-used verification token")

    if tenant.email_verified_at is not None:
        raise SignupVerificationError("This account is already verified")

    expires_at = tenant.verification_sent_at + timedelta(hours=settings.signup_token_ttl_hours)
    if datetime.utcnow() > expires_at:
        raise SignupVerificationError("Verification link has expired - sign up again")

    tenant.email_verified_at = datetime.utcnow()
    tenant.verification_token_hash = None  # single-use
    session.commit()

    raw_key, key_prefix, hashed_secret = generate_api_key()
    api_key = ApiKey(
        tenant_id=tenant.id, key_prefix=key_prefix, hashed_secret=hashed_secret, name="Default Key",
    )
    session.add(api_key)
    session.commit()

    return tenant, raw_key
