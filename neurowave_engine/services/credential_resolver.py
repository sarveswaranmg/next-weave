"""
Resolves a tenant's stored BYOK provider credential (if any) into the
kwargs `get_provider()` expects. Kept separate from `RuntimeOrchestrator`
so the orchestrator's own tests don't need to know about encryption/
`ProviderCredential` at all - callers pass plain kwargs down either way.
"""
from typing import Dict
from uuid import UUID

from sqlalchemy.orm import Session

from neurowave_engine.core.crypto import decrypt_credential
from neurowave_engine.db.models import ProviderCredential


def resolve_provider_kwargs(session: Session, tenant_id: UUID, provider_name: str) -> Dict:
    """
    Returns `{"api_key": ..., "base_url": ...}` for a tenant's stored
    credential, or `{}` if none is configured - callers fall through to
    whatever `get_provider()`'s own defaults are in that case (e.g. the
    server-operator's own key for providers they choose to subsidize).
    """
    credential = (
        session.query(ProviderCredential)
        .filter(ProviderCredential.tenant_id == tenant_id, ProviderCredential.provider == provider_name)
        .first()
    )
    if not credential:
        return {}

    kwargs = {"api_key": decrypt_credential(credential.encrypted_api_key)}
    if credential.base_url_override:
        kwargs["base_url"] = credential.base_url_override
    return kwargs
