"""
Tests for self-serve signup: email verification, first API key issuance, IP
rate limiting, and no-enumeration on repeat/duplicate signups.
"""
import re
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from neurowave_engine.core.config import settings
from neurowave_engine.db.database import get_db
from neurowave_engine.db.models import Tenant
from neurowave_engine.main import app
import neurowave_engine.services.signup_service as signup_service
from neurowave_engine.services.signup_service import (
    SignupRateLimitError,
    SignupVerificationError,
    create_signup,
    verify_signup,
)


@pytest.fixture
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def captured_email(monkeypatch):
    captured = {}

    def fake_send(to_email, verify_url):
        captured["to_email"] = to_email
        captured["verify_url"] = verify_url

    monkeypatch.setattr(signup_service, "send_verification_email", fake_send)
    return captured


class TestSignupFlow:
    def test_signup_creates_unverified_tenant(self, db_session, captured_email):
        create_signup(db_session, email="alice@example.com", company_name="Acme", ip_address="1.1.1.1")

        tenant = db_session.query(Tenant).filter(Tenant.email == "alice@example.com").first()
        assert tenant is not None
        assert tenant.email_verified_at is None
        assert captured_email["to_email"] == "alice@example.com"
        assert "token=" in captured_email["verify_url"]

    def test_verify_with_valid_token_returns_working_key(self, db_session, captured_email):
        create_signup(db_session, email="bob@example.com", company_name="Bobco", ip_address="1.1.1.2")
        token = captured_email["verify_url"].split("token=")[1]

        tenant, api_key = verify_signup(db_session, token)

        assert tenant.email_verified_at is not None
        assert api_key.startswith("nw_live_")

    def test_verify_with_invalid_token_raises(self, db_session):
        with pytest.raises(SignupVerificationError):
            verify_signup(db_session, "not-a-real-token")

    def test_verify_token_is_single_use(self, db_session, captured_email):
        create_signup(db_session, email="carol@example.com", company_name="Carolco", ip_address="1.1.1.3")
        token = captured_email["verify_url"].split("token=")[1]

        verify_signup(db_session, token)
        with pytest.raises(SignupVerificationError):
            verify_signup(db_session, token)

    def test_expired_token_is_rejected(self, db_session, captured_email):
        create_signup(db_session, email="dave@example.com", company_name="Daveco", ip_address="1.1.1.4")
        tenant = db_session.query(Tenant).filter(Tenant.email == "dave@example.com").first()
        tenant.verification_sent_at = datetime.utcnow() - timedelta(hours=settings.signup_token_ttl_hours + 1)
        db_session.commit()
        token = captured_email["verify_url"].split("token=")[1]

        with pytest.raises(SignupVerificationError):
            verify_signup(db_session, token)

    def test_signup_for_already_verified_email_does_not_resend(self, db_session, captured_email):
        create_signup(db_session, email="erin@example.com", company_name="Erinco", ip_address="1.1.1.5")
        token = captured_email["verify_url"].split("token=")[1]
        verify_signup(db_session, token)

        captured_email.clear()
        create_signup(db_session, email="erin@example.com", company_name="Erinco again", ip_address="1.1.1.6")
        assert captured_email == {}  # no new email sent - existing verified account left alone

    def test_ip_rate_limit_blocks_after_max_attempts(self, db_session, captured_email):
        for i in range(settings.signup_max_per_ip_per_day):
            create_signup(db_session, email=f"user{i}@example.com", company_name="X", ip_address="9.9.9.9")

        with pytest.raises(SignupRateLimitError):
            create_signup(db_session, email="onemore@example.com", company_name="X", ip_address="9.9.9.9")


class TestSignupEndpoints:
    def test_get_signup_form_renders(self, client):
        r = client.get("/signup")
        assert r.status_code == 200
        assert "NeuroWeave" in r.text

    def test_post_signup_shows_check_email_page(self, client, captured_email):
        r = client.post("/signup", data={"email": "frank@example.com", "company_name": "Frankco"})
        assert r.status_code == 200
        assert "Check your email" in r.text

    def test_verify_endpoint_shows_api_key(self, client, captured_email):
        client.post("/signup", data={"email": "grace@example.com", "company_name": "Graceco"})
        token = captured_email["verify_url"].split("token=")[1]

        r = client.get(f"/signup/verify?token={token}")
        assert r.status_code == 200
        assert "nw_live_" in r.text

    def test_verify_endpoint_with_bad_token_shows_error(self, client):
        r = client.get("/signup/verify?token=garbage")
        assert r.status_code == 400
        assert "Verification failed" in r.text

    def test_new_key_authenticates_against_runtime_chat(self, client, captured_email):
        client.post("/signup", data={"email": "henry@example.com", "company_name": "Henryco"})
        token = captured_email["verify_url"].split("token=")[1]
        verify_response = client.get(f"/signup/verify?token={token}")

        match = re.search(r'<code class="key">([^<]+)</code>', verify_response.text)
        assert match is not None
        api_key = match.group(1)

        r = client.post(
            "/runtime/chat",
            headers={"X-API-Key": api_key},
            json={
                "user_id": "00000000-0000-0000-0000-000000000001",
                "message": "hello",
                "provider": "echo",
                "schedule_background": False,
            },
        )
        assert r.status_code == 200
        assert r.json()["response"]
