"""
Outbound email for self-serve signup - plain SMTP (stdlib `smtplib`), not a
transactional-email API. NeuroWeave is meant to be self-hostable, so
requiring an account with a third-party email vendor just to verify a
signup would be a worse default than "bring your own SMTP creds" (the same
tradeoff already made for LLM providers via BYOK).

If `settings.smtp_host` is unset, the verification link is logged instead
of emailed - a local-dev/test fallback, the same graceful-degradation
pattern the `echo` LLM provider already uses.
"""
import logging
import smtplib
from email.mime.text import MIMEText

from neurowave_engine.core.config import settings

logger = logging.getLogger(__name__)


def send_verification_email(to_email: str, verify_url: str) -> None:
    if not settings.smtp_host:
        logger.info(f"[dev fallback: SMTP not configured] Verification link for {to_email}: {verify_url}")
        return

    message = MIMEText(
        f"Welcome to NeuroWeave.\n\n"
        f"Verify your email to activate your account and get your API key:\n\n"
        f"{verify_url}\n\n"
        f"This link expires in {settings.signup_token_ttl_hours} hours."
    )
    message["Subject"] = "Verify your NeuroWeave account"
    message["From"] = settings.smtp_from_email
    message["To"] = to_email

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        if settings.smtp_use_tls:
            server.starttls()
        if settings.smtp_username:
            server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, [to_email], message.as_string())
