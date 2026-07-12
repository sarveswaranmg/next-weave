"""Day 7: Cognitive Forgetting & Memory Evolution Engine.

Adds the FORGOTTEN lifecycle state, Day 7 lifecycle fields on memories,
and the memory_events audit table.

Revision ID: 007
Revises: 006
Create Date: 2026-07-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add FORGOTTEN to the existing native Postgres enum type. Must run
    # outside the value's own transaction on older Postgres, but is safe
    # here since it's not referenced by any DML in this same migration.
    op.execute("ALTER TYPE cognitivememorystateenum ADD VALUE IF NOT EXISTS 'FORGOTTEN'")

    # Day 7 lifecycle fields on memories
    op.add_column('memories', sa.Column('entropy_score', sa.Float(), server_default='0.0', nullable=True))
    op.add_column('memories', sa.Column('last_decay_at', sa.DateTime(), nullable=True))
    op.add_column('memories', sa.Column('archive_reason', sa.Text(), nullable=True))
    op.add_column('memories', sa.Column('forget_reason', sa.Text(), nullable=True))
    op.add_column('memories', sa.Column('revival_count', sa.Integer(), server_default='0', nullable=True))

    op.create_index('idx_memory_entropy_score', 'memories', ['entropy_score'], unique=False)
    op.create_index('idx_memory_last_decay_at', 'memories', ['last_decay_at'], unique=False)

    # memory_events audit table
    op.create_table(
        'memory_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('memory_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('old_state', sa.String(50), nullable=True),
        sa.Column('new_state', sa.String(50), nullable=True),
        sa.Column('old_strength', sa.Float(), nullable=True),
        sa.Column('new_strength', sa.Float(), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), default=0.0),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('timestamp', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['memory_id'], ['memories.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_memory_event_memory_id', 'memory_events', ['memory_id'], unique=False)
    op.create_index('idx_memory_event_user_id', 'memory_events', ['user_id'], unique=False)
    op.create_index('idx_memory_event_type', 'memory_events', ['event_type'], unique=False)
    op.create_index('idx_memory_event_timestamp', 'memory_events', ['timestamp'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_memory_event_timestamp', table_name='memory_events')
    op.drop_index('idx_memory_event_type', table_name='memory_events')
    op.drop_index('idx_memory_event_user_id', table_name='memory_events')
    op.drop_index('idx_memory_event_memory_id', table_name='memory_events')
    op.drop_table('memory_events')

    op.drop_index('idx_memory_last_decay_at', table_name='memories')
    op.drop_index('idx_memory_entropy_score', table_name='memories')

    op.drop_column('memories', 'revival_count')
    op.drop_column('memories', 'forget_reason')
    op.drop_column('memories', 'archive_reason')
    op.drop_column('memories', 'last_decay_at')
    op.drop_column('memories', 'entropy_score')

    # Note: Postgres does not support removing a value from an enum type
    # without recreating it; FORGOTTEN is intentionally left in place on
    # downgrade (harmless - it simply becomes unused).
