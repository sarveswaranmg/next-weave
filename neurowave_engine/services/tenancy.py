"""
Tenant/end-user ownership checks.

`Tenant` (see `neurowave_engine.db.models`) is the SaaS auth boundary; every `user_id`
referenced in a request body/path/query param must belong to the
authenticated tenant before any service touches that user's data. This is
what stops one tenant from reading or deleting another tenant's end-user
data just by guessing/enumerating UUIDs - the core gap in the old model,
where a single shared `RUNTIME_API_KEY` gated the whole deployment but a
client-supplied `user_id` was trusted with no ownership check at all.
"""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from neurowave_engine.db.models import User


def get_owned_user_or_404(session: Session, user_id: UUID, tenant_id: UUID) -> User:
    """
    For read/delete endpoints: the user must already exist and belong to
    the authenticated tenant. Never auto-creates - use
    `get_or_create_owned_user` for the chat ingestion path, where a first
    message for a brand-new `user_id` is expected to create it.
    """
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"No user {user_id}")
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="This user belongs to a different tenant")
    return user


def get_or_create_owned_user(session: Session, user_id: UUID, tenant_id: UUID) -> User:
    """
    For the chat ingestion path: a first message for a new `user_id`
    creates it under the calling tenant; a `user_id` that already exists
    under a *different* tenant is rejected rather than silently reused.
    """
    user = session.query(User).filter(User.id == user_id).first()
    if user:
        if user.tenant_id != tenant_id:
            raise HTTPException(status_code=403, detail="This user belongs to a different tenant")
        return user

    user = User(id=user_id, tenant_id=tenant_id, external_id=str(user_id))
    session.add(user)
    session.commit()
    return user
