"""
Free-tier monthly usage cap enforcement - but **only** for tenants that came
through the public self-serve signup flow (see
`neurowave_engine.services.signup_service`). A tenant you create for
yourself via `scripts/bootstrap_tenant.py` never sets `email_verified_at`
(only `verify_signup()` does), which is what distinguishes "a stranger who
signed up on the public /signup page" from "the operator's own tenant" -
self-hosting for your own use is not capped by this at all. Called from the
`/runtime/chat` route *before* the LLM call (see
`neurowave_engine/api/runtime.py`), not after: this is a hard cost cap, so
the call that would exceed it must never actually reach the provider.
"""
from datetime import date, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.core.config import settings
from neurowave_engine.db.models import Tenant, TenantUsage


class UsageLimitExceeded(Exception):
    """Raised when a self-serve-signup tenant has hit
    settings.free_tier_monthly_chat_limit for the current month."""


def check_and_increment(session: Session, tenant_id: UUID) -> None:
    tenant = session.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None or tenant.email_verified_at is None:
        # Not a self-serve-signup tenant (e.g. bootstrap_tenant.py) - no cap.
        return

    period_start = date.today().replace(day=1)

    usage = (
        session.query(TenantUsage)
        .filter(TenantUsage.tenant_id == tenant_id, TenantUsage.period_start == period_start)
        .first()
    )
    if usage is None:
        usage = TenantUsage(tenant_id=tenant_id, period_start=period_start, chat_call_count=0)
        session.add(usage)

    if usage.chat_call_count >= settings.free_tier_monthly_chat_limit:
        raise UsageLimitExceeded(
            f"Monthly usage limit of {settings.free_tier_monthly_chat_limit} chat calls reached "
            f"for this billing period"
        )

    usage.chat_call_count += 1
    usage.updated_at = datetime.utcnow()
    session.commit()
