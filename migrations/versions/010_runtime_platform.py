"""Day 10: Cognitive Runtime Platform, SDK & Benchmark Suite.

Adds benchmark_runs and runtime_metrics.

Revision ID: 010
Revises: 009
Create Date: 2026-07-10 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'benchmark_runs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('strategy', sa.String(100), nullable=False),
        sa.Column('model', sa.String(100), nullable=True),
        sa.Column('dataset', sa.String(255), nullable=False),
        sa.Column('latency_ms', sa.Float(), default=0.0),
        sa.Column('token_usage', sa.Integer(), default=0),
        sa.Column('prompt_token_reduction_percent', sa.Float(), default=0.0),
        sa.Column('memory_precision', sa.Float(), default=0.0),
        sa.Column('memory_recall', sa.Float(), default=0.0),
        sa.Column('task_completion_score', sa.Float(), default=0.0),
        sa.Column('personalization_score', sa.Float(), default=0.0),
        sa.Column('reasoning_score', sa.Float(), default=0.0),
        sa.Column('hallucination_rate', sa.Float(), default=0.0),
        sa.Column('long_term_consistency_score', sa.Float(), default=0.0),
        sa.Column('identity_continuity_score', sa.Float(), default=0.0),
        sa.Column('world_model_accuracy', sa.Float(), default=0.0),
        sa.Column('storage_growth_bytes', sa.Integer(), default=0),
        sa.Column('compression_ratio', sa.Float(), default=0.0),
        sa.Column('cost_usd', sa.Float(), default=0.0),
        sa.Column('interaction_count', sa.Integer(), default=0),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_benchmark_run_user_id', 'benchmark_runs', ['user_id'], unique=False)
    op.create_index('idx_benchmark_run_strategy', 'benchmark_runs', ['strategy'], unique=False)
    op.create_index('idx_benchmark_run_dataset', 'benchmark_runs', ['dataset'], unique=False)
    op.create_index('idx_benchmark_run_created_at', 'benchmark_runs', ['created_at'], unique=False)

    op.create_table(
        'runtime_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('memory_count', sa.Integer(), default=0),
        sa.Column('concept_count', sa.Integer(), default=0),
        sa.Column('identity_nodes', sa.Integer(), default=0),
        sa.Column('world_nodes', sa.Integer(), default=0),
        sa.Column('world_relationships', sa.Integer(), default=0),
        sa.Column('project_count', sa.Integer(), default=0),
        sa.Column('compression_ratio', sa.Float(), default=0.0),
        sa.Column('cognitive_health_score', sa.Float(), default=0.0),
        sa.Column('latency_ms', sa.Float(), default=0.0),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_runtime_metrics_user_id', 'runtime_metrics', ['user_id'], unique=False)
    op.create_index('idx_runtime_metrics_created_at', 'runtime_metrics', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_runtime_metrics_created_at', table_name='runtime_metrics')
    op.drop_index('idx_runtime_metrics_user_id', table_name='runtime_metrics')
    op.drop_table('runtime_metrics')

    op.drop_index('idx_benchmark_run_created_at', table_name='benchmark_runs')
    op.drop_index('idx_benchmark_run_dataset', table_name='benchmark_runs')
    op.drop_index('idx_benchmark_run_strategy', table_name='benchmark_runs')
    op.drop_index('idx_benchmark_run_user_id', table_name='benchmark_runs')
    op.drop_table('benchmark_runs')
