"""Day 8: Offline Cognitive Consolidation Engine ("Dream Mode").

Adds dream_sessions, knowledge_synthesis, and identity_evolution_events.

Revision ID: 008
Revises: 007
Create Date: 2026-07-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    dream_status_enum = postgresql.ENUM(
        'RUNNING', 'COMPLETED', 'CANCELLED', 'FAILED',
        name='dreamsessionstatusenum'
    )
    dream_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'dream_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.Enum('RUNNING', 'COMPLETED', 'CANCELLED', 'FAILED', name='dreamsessionstatusenum'), nullable=True, server_default='RUNNING'),
        sa.Column('trigger', sa.String(50), server_default='manual'),
        sa.Column('started_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('memories_replayed', sa.Integer(), default=0),
        sa.Column('memories_processed', sa.Integer(), default=0),
        sa.Column('patterns_discovered', sa.Integer(), default=0),
        sa.Column('concepts_created', sa.Integer(), default=0),
        sa.Column('concepts_refined', sa.Integer(), default=0),
        sa.Column('identity_updates', sa.Integer(), default=0),
        sa.Column('contradictions_resolved', sa.Integer(), default=0),
        sa.Column('graph_nodes_removed', sa.Integer(), default=0),
        sa.Column('graph_edges_strengthened', sa.Integer(), default=0),
        sa.Column('knowledge_synthesized', sa.Integer(), default=0),
        sa.Column('compression_ratio', sa.Float(), default=0.0),
        sa.Column('health_score_before', sa.Float(), nullable=True),
        sa.Column('health_score_after', sa.Float(), nullable=True),
        sa.Column('stage_latency_ms', postgresql.JSON(), default={}),
        sa.Column('total_latency_ms', sa.Float(), default=0.0),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_dream_session_user_id', 'dream_sessions', ['user_id'], unique=False)
    op.create_index('idx_dream_session_status', 'dream_sessions', ['status'], unique=False)
    op.create_index('idx_dream_session_started_at', 'dream_sessions', ['started_at'], unique=False)

    op.create_table(
        'knowledge_synthesis',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('dream_session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('source_concept_ids', postgresql.JSON(), default=[]),
        sa.Column('source_concept_names', postgresql.JSON(), default=[]),
        sa.Column('new_concept_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('new_concept', sa.String(255), nullable=False),
        sa.Column('reasoning', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), default=0.0),
        sa.Column('generated_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['dream_session_id'], ['dream_sessions.id'], ),
        sa.ForeignKeyConstraint(['new_concept_id'], ['concept_memories.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_knowledge_synthesis_user_id', 'knowledge_synthesis', ['user_id'], unique=False)
    op.create_index('idx_knowledge_synthesis_session_id', 'knowledge_synthesis', ['dream_session_id'], unique=False)
    op.create_index('idx_knowledge_synthesis_generated_at', 'knowledge_synthesis', ['generated_at'], unique=False)

    op.create_table(
        'identity_evolution_events',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('dream_session_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('old_identity', sa.String(255), nullable=True),
        sa.Column('new_identity', sa.String(255), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('evidence_concept_ids', postgresql.JSON(), default=[]),
        sa.Column('confidence', sa.Float(), default=0.0),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['dream_session_id'], ['dream_sessions.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_identity_evolution_user_id', 'identity_evolution_events', ['user_id'], unique=False)
    op.create_index('idx_identity_evolution_session_id', 'identity_evolution_events', ['dream_session_id'], unique=False)
    op.create_index('idx_identity_evolution_created_at', 'identity_evolution_events', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_identity_evolution_created_at', table_name='identity_evolution_events')
    op.drop_index('idx_identity_evolution_session_id', table_name='identity_evolution_events')
    op.drop_index('idx_identity_evolution_user_id', table_name='identity_evolution_events')
    op.drop_table('identity_evolution_events')

    op.drop_index('idx_knowledge_synthesis_generated_at', table_name='knowledge_synthesis')
    op.drop_index('idx_knowledge_synthesis_session_id', table_name='knowledge_synthesis')
    op.drop_index('idx_knowledge_synthesis_user_id', table_name='knowledge_synthesis')
    op.drop_table('knowledge_synthesis')

    op.drop_index('idx_dream_session_started_at', table_name='dream_sessions')
    op.drop_index('idx_dream_session_status', table_name='dream_sessions')
    op.drop_index('idx_dream_session_user_id', table_name='dream_sessions')
    op.drop_table('dream_sessions')

    postgresql.ENUM(name='dreamsessionstatusenum').drop(op.get_bind(), checkfirst=True)
