"""Multi-tenant API key auth, replacing the single shared RUNTIME_API_KEY.

Adds `tenants` (the SaaS billing/auth boundary - a Tenant manages many
`users`, e.g. a customer support bot built on NeuroWeave has one Tenant -
the company running it - and one `User` per end-user the bot has talked
to), a `tenant_id` FK on `users`, `api_keys` (per-tenant, hashed,
revocable, roled credentials), and `provider_credentials` (encrypted BYOK
LLM keys per tenant/provider, shared across all of that tenant's users).

If `RUNTIME_API_KEY` is set in the environment at migration time, this
also bootstraps exactly one Tenant + one User (if none exist) + one ApiKey
hashing that value, so an existing single-tenant deployment's key keeps
working post-upgrade instead of being locked out.

Revision ID: 011
Revises: 010
Create Date: 2026-07-23 00:00:00.000000

"""
import hashlib
import os
import uuid
from datetime import datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None

_KEY_PREFIX_LEN = 12


def upgrade() -> None:
    op.create_table(
        'tenants',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )

    # Every existing user_id-scoped table stays as-is; only `users` gets a
    # new tenant_id FK. Nullable at first so existing rows don't break the
    # ADD COLUMN, then backfilled and tightened to NOT NULL below.
    op.add_column('users', sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index('idx_user_tenant_id', 'users', ['tenant_id'], unique=False)
    _backfill_tenant_for_existing_users()
    op.alter_column('users', 'tenant_id', nullable=False)
    op.create_foreign_key('fk_users_tenant_id', 'users', 'tenants', ['tenant_id'], ['id'])

    op.create_table(
        'api_keys',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('key_prefix', sa.String(12), nullable=False),
        sa.Column('hashed_secret', sa.String(255), nullable=False),
        sa.Column('role', sa.Enum('admin', 'developer', 'readonly', name='apikeyrole'), nullable=False,
                  server_default='developer'),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(), nullable=True),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_api_key_tenant_id', 'api_keys', ['tenant_id'], unique=False)
    op.create_index('idx_api_key_prefix', 'api_keys', ['key_prefix'], unique=False)

    op.create_table(
        'provider_credentials',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('encrypted_api_key', sa.Text(), nullable=False),
        sa.Column('base_url_override', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_provider_cred_tenant_provider', 'provider_credentials',
                     ['tenant_id', 'provider'], unique=True)

    _bootstrap_from_legacy_runtime_api_key()


def _backfill_tenant_for_existing_users() -> None:
    """
    Pre-existing deployments may already have `users` rows from before
    tenancy existed. Group them all under one auto-created tenant per
    upgrade (there is no way to infer separate real tenants from data that
    predates the concept) rather than leaving tenant_id null.
    """
    conn = op.get_bind()
    existing_users = conn.execute(sa.text("SELECT id FROM users")).fetchall()
    if not existing_users:
        return

    tenant_id = uuid.uuid4()
    conn.execute(
        sa.text(
            "INSERT INTO tenants (id, name, email, created_at, updated_at) "
            "VALUES (:id, :name, :email, :now, :now)"
        ),
        {"id": str(tenant_id), "name": "Migrated tenant (pre-existing users)",
         "email": f"migrated-{tenant_id}@internal.neuroweave", "now": datetime.utcnow()},
    )
    conn.execute(
        sa.text("UPDATE users SET tenant_id = :tenant_id WHERE tenant_id IS NULL"),
        {"tenant_id": str(tenant_id)},
    )


def _bootstrap_from_legacy_runtime_api_key() -> None:
    """
    Soft-landing for existing single-tenant deployments: if RUNTIME_API_KEY
    is set in the migration's environment, create one Tenant (reusing the
    one from `_backfill_tenant_for_existing_users` if pre-existing users
    were found, otherwise a fresh one) + one ApiKey hashing that value, so
    the operator's existing key keeps working post-upgrade instead of
    needing a manual re-key.
    """
    legacy_key = os.environ.get("RUNTIME_API_KEY")
    if not legacy_key:
        return

    conn = op.get_bind()
    existing_tenant = conn.execute(sa.text("SELECT id FROM tenants LIMIT 1")).first()

    if existing_tenant:
        tenant_id = existing_tenant[0]
    else:
        tenant_id = uuid.uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO tenants (id, name, email, created_at, updated_at) "
                "VALUES (:id, :name, :email, :now, :now)"
            ),
            {"id": str(tenant_id), "name": "Bootstrapped tenant",
             "email": f"bootstrap-{tenant_id}@internal.neuroweave", "now": datetime.utcnow()},
        )

    hashed_secret = hashlib.sha256(legacy_key.encode()).hexdigest()
    conn.execute(
        sa.text(
            "INSERT INTO api_keys (id, tenant_id, key_prefix, hashed_secret, role, name, created_at) "
            "VALUES (:id, :tenant_id, :key_prefix, :hashed_secret, :role, :name, :now)"
        ),
        {
            "id": str(uuid.uuid4()), "tenant_id": str(tenant_id),
            "key_prefix": legacy_key[:_KEY_PREFIX_LEN], "hashed_secret": hashed_secret,
            "role": "admin", "name": "Bootstrapped from legacy RUNTIME_API_KEY", "now": datetime.utcnow(),
        },
    )


def downgrade() -> None:
    op.drop_index('idx_provider_cred_tenant_provider', table_name='provider_credentials')
    op.drop_table('provider_credentials')

    op.drop_index('idx_api_key_prefix', table_name='api_keys')
    op.drop_index('idx_api_key_tenant_id', table_name='api_keys')
    op.drop_table('api_keys')

    op.drop_constraint('fk_users_tenant_id', 'users', type_='foreignkey')
    op.drop_index('idx_user_tenant_id', table_name='users')
    op.drop_column('users', 'tenant_id')

    op.drop_table('tenants')

    sa.Enum(name='apikeyrole').drop(op.get_bind(), checkfirst=True)
