"""
HTTP-layer tests for the multi-tenant auth/RBAC/ownership model
(app.core.security, app.services.tenancy). Everything else in this suite
exercises services directly against a session; this file is the one place
that drives requests through the real FastAPI dependency chain (TestClient
+ a dependency override on `get_db`), since that's the only way to catch
wiring bugs in the routes themselves (missing Depends, wrong permission,
etc.) rather than just the underlying service logic.
"""
import pytest
from fastapi.testclient import TestClient

from app.core.security import generate_api_key
from app.db.database import get_db
from app.db.models import ApiKey, Role, Tenant
from app.main import app


@pytest.fixture
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def make_api_key(db_session, tenant_id, role=Role.DEVELOPER):
    raw_key, key_prefix, hashed_secret = generate_api_key()
    api_key = ApiKey(tenant_id=tenant_id, key_prefix=key_prefix, hashed_secret=hashed_secret, role=role)
    db_session.add(api_key)
    db_session.commit()
    return raw_key


class TestApiKeyAuth:
    def test_missing_key_is_rejected(self, client):
        r = client.post("/runtime/chat", json={"user_id": "00000000-0000-0000-0000-000000000001", "message": "hi"})
        assert r.status_code == 401

    def test_unknown_key_is_rejected(self, client):
        r = client.post(
            "/runtime/chat", json={"user_id": "00000000-0000-0000-0000-000000000001", "message": "hi"},
            headers={"X-API-Key": "nw_live_totally-made-up"},
        )
        assert r.status_code == 401

    def test_revoked_key_is_rejected(self, client, db_session, tenant):
        from datetime import datetime
        raw_key = make_api_key(db_session, tenant.id)
        key_row = db_session.query(ApiKey).filter(ApiKey.tenant_id == tenant.id).first()
        key_row.revoked_at = datetime.utcnow()
        db_session.commit()

        r = client.get("/runtime/metrics?user_id=00000000-0000-0000-0000-000000000001", headers={"X-API-Key": raw_key})
        assert r.status_code == 401

    def test_valid_key_authenticates(self, client, db_session, tenant, user):
        raw_key = make_api_key(db_session, tenant.id)
        r = client.post(
            "/runtime/chat", json={"user_id": str(user.id), "message": "hi", "provider": "echo",
                                    "schedule_background": False},
            headers={"X-API-Key": raw_key},
        )
        assert r.status_code == 200

    def test_health_and_version_need_no_key(self, client):
        assert client.get("/runtime/health").status_code == 200
        assert client.get("/runtime/version").status_code == 200


class TestRBAC:
    def test_readonly_key_cannot_write(self, client, db_session, tenant, user):
        raw_key = make_api_key(db_session, tenant.id, role=Role.READONLY)
        r = client.post(
            "/runtime/chat", json={"user_id": str(user.id), "message": "hi", "provider": "echo"},
            headers={"X-API-Key": raw_key},
        )
        assert r.status_code == 403

    def test_readonly_key_can_read(self, client, db_session, tenant, user):
        raw_key = make_api_key(db_session, tenant.id, role=Role.READONLY)
        r = client.get(f"/runtime/metrics?user_id={user.id}", headers={"X-API-Key": raw_key})
        assert r.status_code == 200

    def test_developer_key_cannot_delete(self, client, db_session, tenant, user):
        raw_key = make_api_key(db_session, tenant.id, role=Role.DEVELOPER)
        r = client.delete(f"/runtime/users/{user.id}", headers={"X-API-Key": raw_key})
        assert r.status_code == 403

    def test_admin_key_can_delete(self, client, db_session, tenant, user):
        raw_key = make_api_key(db_session, tenant.id, role=Role.ADMIN)
        r = client.delete(f"/runtime/users/{user.id}", headers={"X-API-Key": raw_key})
        assert r.status_code == 200

    def test_non_admin_cannot_mint_keys(self, client, db_session, tenant):
        raw_key = make_api_key(db_session, tenant.id, role=Role.DEVELOPER)
        r = client.post("/runtime/keys", json={"name": "x"}, headers={"X-API-Key": raw_key})
        assert r.status_code == 403


class TestCrossTenantIsolation:
    """The core fix: a client-supplied user_id must never let one tenant
    touch another tenant's data, even with a completely valid key."""

    def test_cannot_read_another_tenants_user_metrics(self, client, db_session, tenant, user):
        other_tenant = Tenant(name="Other", email="other@example.com")
        db_session.add(other_tenant)
        db_session.commit()
        other_key = make_api_key(db_session, other_tenant.id)

        r = client.get(f"/runtime/metrics?user_id={user.id}", headers={"X-API-Key": other_key})
        assert r.status_code == 403

    def test_cannot_chat_as_another_tenants_user(self, client, db_session, tenant, user):
        other_tenant = Tenant(name="Other", email="other2@example.com")
        db_session.add(other_tenant)
        db_session.commit()
        other_key = make_api_key(db_session, other_tenant.id)

        r = client.post(
            "/runtime/chat", json={"user_id": str(user.id), "message": "sneaky", "provider": "echo",
                                    "schedule_background": False},
            headers={"X-API-Key": other_key},
        )
        assert r.status_code == 403

    def test_cannot_delete_another_tenants_user(self, client, db_session, tenant, user):
        other_tenant = Tenant(name="Other", email="other3@example.com")
        db_session.add(other_tenant)
        db_session.commit()
        other_admin_key = make_api_key(db_session, other_tenant.id, role=Role.ADMIN)

        r = client.delete(f"/runtime/users/{user.id}", headers={"X-API-Key": other_admin_key})
        assert r.status_code == 403

    def test_metrics_for_nonexistent_user_is_404(self, client, db_session, tenant):
        from uuid import uuid4
        raw_key = make_api_key(db_session, tenant.id)
        r = client.get(f"/runtime/metrics?user_id={uuid4()}", headers={"X-API-Key": raw_key})
        assert r.status_code == 404


class TestApiKeyManagement:
    def test_admin_can_create_list_and_revoke_keys(self, client, db_session, tenant):
        admin_key = make_api_key(db_session, tenant.id, role=Role.ADMIN)

        r = client.post("/runtime/keys", json={"name": "second key", "role": "readonly"},
                         headers={"X-API-Key": admin_key})
        assert r.status_code == 200
        new_key_id = r.json()["id"]
        new_key = r.json()["api_key"]

        r = client.get("/runtime/keys", headers={"X-API-Key": admin_key})
        assert r.status_code == 200
        assert len(r.json()["keys"]) == 2

        r = client.delete(f"/runtime/keys/{new_key_id}", headers={"X-API-Key": admin_key})
        assert r.status_code == 200

        # revoked key no longer authenticates
        r = client.get("/runtime/health", headers={"X-API-Key": new_key})
        assert r.status_code == 200  # /health needs no key at all
        r = client.get("/runtime/keys", headers={"X-API-Key": new_key})
        assert r.status_code == 401
