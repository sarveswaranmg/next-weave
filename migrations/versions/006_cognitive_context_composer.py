"""Day 6: Cognitive Context Composer - Add context_snapshots and context_metrics.

Revision ID: 006
Revises: 005
Create Date: 2026-07-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'context_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('detected_goal', sa.String(100), nullable=True),
        sa.Column('generated_context', sa.Text(), nullable=False),
        sa.Column('narrative', sa.Text(), nullable=True),
        sa.Column('context_quality', sa.Float(), default=0.0),
        sa.Column('token_count', sa.Integer(), default=0),
        sa.Column('original_token_count', sa.Integer(), default=0),
        sa.Column('compression_ratio', sa.Float(), default=0.0),
        sa.Column('contradiction_count', sa.Integer(), default=0),
        sa.Column('missing_topics', postgresql.JSON(), default=[]),
        sa.Column('source_memory_ids', postgresql.JSON(), default=[]),
        sa.Column('total_latency_ms', sa.Float(), default=0.0),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_context_snapshot_user_id', 'context_snapshots', ['user_id'], unique=False)
    op.create_index('idx_context_snapshot_created_at', 'context_snapshots', ['created_at'], unique=False)
    op.create_index('idx_context_snapshot_goal', 'context_snapshots', ['detected_goal'], unique=False)
    op.create_index('idx_context_snapshot_quality', 'context_snapshots', ['context_quality'], unique=False)

    op.create_table(
        'context_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('snapshot_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('coverage', sa.Float(), default=0.0),
        sa.Column('redundancy', sa.Float(), default=0.0),
        sa.Column('identity_alignment', sa.Float(), default=0.0),
        sa.Column('goal_alignment', sa.Float(), default=0.0),
        sa.Column('quality_score', sa.Float(), default=0.0),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['snapshot_id'], ['context_snapshots.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_context_metrics_snapshot_id', 'context_metrics', ['snapshot_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_context_metrics_snapshot_id', table_name='context_metrics')
    op.drop_table('context_metrics')

    op.drop_index('idx_context_snapshot_quality', table_name='context_snapshots')
    op.drop_index('idx_context_snapshot_goal', table_name='context_snapshots')
    op.drop_index('idx_context_snapshot_created_at', table_name='context_snapshots')
    op.drop_index('idx_context_snapshot_user_id', table_name='context_snapshots')
    op.drop_table('context_snapshots')
