"""Self-serve signup: email verification on `tenants`, a per-tenant monthly
usage counter (`tenant_usage`) enforcing the free-tier cap, and an IP-based
abuse-protection log for the signup endpoint (`signup_attempts`).

Pre-existing tenants (bootstrapped via `scripts/bootstrap_tenant.py` or the
legacy-key migration in 011) are left with `email_verified_at` NULL - they
didn't go through this flow and aren't gated by it (only the self-serve
signup route checks verification status).

Revision ID: 012
Revises: 011
Create Date: 2026-08-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tenants', sa.Column('email_verified_at', sa.DateTime(), nullable=True))
    op.add_column('tenants', sa.Column('verification_token_hash', sa.String(64), nullable=True))
    op.add_column('tenants', sa.Column('verification_sent_at', sa.DateTime(), nullable=True))

    op.create_table(
        'tenant_usage',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('tenant_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('chat_call_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_tenant_usage_tenant_period', 'tenant_usage',
                     ['tenant_id', 'period_start'], unique=True)

    op.create_table(
        'signup_attempts',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ip_address', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_signup_attempt_ip_created', 'signup_attempts',
                     ['ip_address', 'created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_signup_attempt_ip_created', table_name='signup_attempts')
    op.drop_table('signup_attempts')

    op.drop_index('idx_tenant_usage_tenant_period', table_name='tenant_usage')
    op.drop_table('tenant_usage')

    op.drop_column('tenants', 'verification_sent_at')
    op.drop_column('tenants', 'verification_token_hash')
    op.drop_column('tenants', 'email_verified_at')
