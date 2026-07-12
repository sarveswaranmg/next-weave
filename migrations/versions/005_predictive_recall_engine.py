"""Day 5: Predictive Recall Engine - Add utility prediction fields and recall logs.

Revision ID: 005
Revises: 004
Create Date: 2026-07-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add predictive utility fields to memories table
    op.add_column('memories', sa.Column('goal_alignment_score', sa.Float(), server_default='0.0', nullable=True))
    op.add_column('memories', sa.Column('utility_score', sa.Float(), server_default='0.0', nullable=True))
    op.add_column('memories', sa.Column('selection_reason', sa.Text(), nullable=True))
    op.add_column('memories', sa.Column('prediction_confidence', sa.Float(), server_default='0.0', nullable=True))
    op.add_column('memories', sa.Column('retrieval_rank', sa.Integer(), nullable=True))
    op.add_column('memories', sa.Column('last_prediction_time', sa.DateTime(), nullable=True))

    op.create_index('idx_memory_utility_score', 'memories', ['utility_score'], unique=False)
    op.create_index('idx_memory_retrieval_rank', 'memories', ['retrieval_rank'], unique=False)

    # Create predictive_recall_logs table
    op.create_table(
        'predictive_recall_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('query', sa.Text(), nullable=False),
        sa.Column('detected_goal', sa.String(100), nullable=True),
        sa.Column('goal_confidence', sa.Float(), default=0.0),
        sa.Column('intents', postgresql.JSON(), default={}),
        sa.Column('candidate_count', sa.Integer(), default=0),
        sa.Column('selected_memory_ids', postgresql.JSON(), default=[]),
        sa.Column('explanations', postgresql.JSON(), default=[]),
        sa.Column('token_budget', sa.Integer(), nullable=True),
        sa.Column('estimated_tokens', sa.Integer(), nullable=True),
        sa.Column('average_utility_score', sa.Float(), default=0.0),
        sa.Column('goal_detection_latency_ms', sa.Float(), default=0.0),
        sa.Column('intent_classification_latency_ms', sa.Float(), default=0.0),
        sa.Column('candidate_retrieval_latency_ms', sa.Float(), default=0.0),
        sa.Column('utility_prediction_latency_ms', sa.Float(), default=0.0),
        sa.Column('ranking_latency_ms', sa.Float(), default=0.0),
        sa.Column('token_optimization_latency_ms', sa.Float(), default=0.0),
        sa.Column('context_assembly_latency_ms', sa.Float(), default=0.0),
        sa.Column('total_latency_ms', sa.Float(), default=0.0),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_recall_log_user_id', 'predictive_recall_logs', ['user_id'], unique=False)
    op.create_index('idx_recall_log_created_at', 'predictive_recall_logs', ['created_at'], unique=False)
    op.create_index('idx_recall_log_goal', 'predictive_recall_logs', ['detected_goal'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_recall_log_goal', table_name='predictive_recall_logs')
    op.drop_index('idx_recall_log_created_at', table_name='predictive_recall_logs')
    op.drop_index('idx_recall_log_user_id', table_name='predictive_recall_logs')
    op.drop_table('predictive_recall_logs')

    op.drop_index('idx_memory_retrieval_rank', table_name='memories')
    op.drop_index('idx_memory_utility_score', table_name='memories')

    op.drop_column('memories', 'last_prediction_time')
    op.drop_column('memories', 'retrieval_rank')
    op.drop_column('memories', 'prediction_confidence')
    op.drop_column('memories', 'selection_reason')
    op.drop_column('memories', 'utility_score')
    op.drop_column('memories', 'goal_alignment_score')
