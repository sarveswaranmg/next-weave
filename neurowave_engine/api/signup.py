"""
Self-serve tenant signup: public web pages + form endpoints, no API key
required (that's the whole point). See
`neurowave_engine.services.signup_service` for the actual logic.
"""
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from neurowave_engine.db.database import get_db
from neurowave_engine.services.signup_service import (
    SignupRateLimitError,
    SignupVerificationError,
    create_signup,
    verify_signup,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["signup"])

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def _client_ip(request: Request) -> str:
    # Trusts request.client.host, which Starlette populates from
    # X-Forwarded-For when uvicorn is run with --proxy-headers (required in
    # production - see docker-compose.prod.yml, Caddy is the only public
    # entry point there). Without that flag this instead reflects the
    # direct connecting peer, which is fine for local/dev use.
    return request.client.host if request.client else "unknown"


@router.get("/signup", response_class=HTMLResponse)
async def signup_form(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})


@router.post("/signup", response_class=HTMLResponse)
async def signup_submit(
    request: Request,
    email: str = Form(...),
    company_name: str = Form(""),
    session: Session = Depends(get_db),
):
    try:
        create_signup(
            session,
            email=email.strip().lower(),
            company_name=company_name.strip(),
            ip_address=_client_ip(request),
        )
    except SignupRateLimitError as e:
        return templates.TemplateResponse(
            "signup.html", {"request": request, "error": str(e)}, status_code=429,
        )
    return templates.TemplateResponse("check_email.html", {"request": request, "email": email})


@router.get("/signup/verify", response_class=HTMLResponse)
async def signup_verify(request: Request, token: str = "", session: Session = Depends(get_db)):
    try:
        tenant, api_key = verify_signup(session, token)
    except SignupVerificationError as e:
        return templates.TemplateResponse(
            "verify_error.html", {"request": request, "error": str(e)}, status_code=400,
        )
    return templates.TemplateResponse(
        "verify_success.html",
        {"request": request, "api_key": api_key, "tenant_name": tenant.name, "base_url": str(request.base_url)},
    )
