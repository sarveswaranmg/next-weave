"""
Tests for the free-tier monthly usage cap (neurowave_engine.services.usage_limiter).
Only tenants that came through the public self-serve /signup flow are
capped - `tenant.email_verified_at` is what distinguishes them from a
tenant the operator created for their own use (scripts/bootstrap_tenant.py),
which is never capped.
"""
from datetime import date, datetime

import pytest

from neurowave_engine.core.config import settings
from neurowave_engine.db.models import TenantUsage
from neurowave_engine.services.usage_limiter import UsageLimitExceeded, check_and_increment


@pytest.fixture
def self_serve_tenant(tenant, db_session):
    """The plain `tenant` fixture (conftest.py) has no email_verified_at -
    that's what a bootstrap_tenant.py-created tenant looks like. Mark it
    verified to simulate a tenant that went through public signup."""
    tenant.email_verified_at = datetime.utcnow()
    db_session.commit()
    return tenant


class TestUsageLimiter:
    def test_allows_calls_up_to_the_cap(self, db_session, self_serve_tenant):
        for _ in range(settings.free_tier_monthly_chat_limit):
            check_and_increment(db_session, self_serve_tenant.id)  # must not raise

    def test_rejects_the_call_after_the_cap(self, db_session, self_serve_tenant):
        for _ in range(settings.free_tier_monthly_chat_limit):
            check_and_increment(db_session, self_serve_tenant.id)

        with pytest.raises(UsageLimitExceeded):
            check_and_increment(db_session, self_serve_tenant.id)

    def test_new_month_resets_the_count(self, db_session, self_serve_tenant):
        for _ in range(settings.free_tier_monthly_chat_limit):
            check_and_increment(db_session, self_serve_tenant.id)

        # Simulate "last month" by moving the existing row's period_start back.
        usage = db_session.query(TenantUsage).filter(TenantUsage.tenant_id == self_serve_tenant.id).first()
        usage.period_start = date(2020, 1, 1)
        db_session.commit()

        check_and_increment(db_session, self_serve_tenant.id)  # must not raise - new month, fresh row

    def test_bootstrap_tenant_is_never_capped(self, db_session, tenant):
        """A plain bootstrap_tenant.py-style tenant (no email_verified_at) -
        self-hosting for your own use is unlimited."""
        for _ in range(settings.free_tier_monthly_chat_limit + 50):
            check_and_increment(db_session, tenant.id)  # must never raise

        # And it shouldn't even be tracked - no TenantUsage row created for it.
        assert db_session.query(TenantUsage).filter(TenantUsage.tenant_id == tenant.id).count() == 0
