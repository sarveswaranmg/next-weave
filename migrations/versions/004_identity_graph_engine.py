"""Day 4: Identity Graph Engine - Add identity nodes, relationships, and history tables.

Revision ID: 004
Revises: 003
Create Date: 2026-06-12 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create identity_nodes table
    op.create_table(
        'identity_nodes',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('node_type', sa.String(50), nullable=False),
        sa.Column('node_value', sa.String(255), nullable=False),
        sa.Column('confidence', sa.Float(), default=0.0),
        sa.Column('evidence_count', sa.Integer(), default=1),
        sa.Column('supporting_memory_ids', postgresql.JSON(), default=[]),
        sa.Column('supporting_concept_ids', postgresql.JSON(), default=[]),
        sa.Column('progression_level', sa.String(50), nullable=True),
        sa.Column('progression_score', sa.Float(), default=0.0),
        sa.Column('last_reinforced_at', sa.DateTime(), nullable=True),
        sa.Column('reinforcement_count', sa.Integer(), default=0),
        sa.Column('decay_rate', sa.Float(), default=0.02),
        sa.Column('related_node_ids', postgresql.JSON(), default=[]),
        sa.Column('importance', sa.Float(), default=0.5),
        sa.Column('embedding', sa.String(255), nullable=True),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_identity_node_user_id', 'identity_nodes', ['user_id'], unique=False)
    op.create_index('idx_identity_node_type', 'identity_nodes', ['node_type'], unique=False)
    op.create_index('idx_identity_node_value', 'identity_nodes', ['node_value'], unique=False)
    op.create_index('idx_identity_node_confidence', 'identity_nodes', ['confidence'], unique=False)
    op.create_index('idx_identity_node_importance', 'identity_nodes', ['importance'], unique=False)
    op.create_index('idx_identity_node_created_at', 'identity_nodes', ['created_at'], unique=False)

    # Create identity_relationships table
    op.create_table(
        'identity_relationships',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_node_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_node_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('relationship_type', sa.String(50), nullable=False),
        sa.Column('strength', sa.Float(), default=0.5),
        sa.Column('reinforcement_count', sa.Integer(), default=1),
        sa.Column('last_reinforced_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['source_node_id'], ['identity_nodes.id'], ),
        sa.ForeignKeyConstraint(['target_node_id'], ['identity_nodes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_identity_rel_user_id', 'identity_relationships', ['user_id'], unique=False)
    op.create_index('idx_identity_rel_source', 'identity_relationships', ['source_node_id'], unique=False)
    op.create_index('idx_identity_rel_target', 'identity_relationships', ['target_node_id'], unique=False)
    op.create_index('idx_identity_rel_type', 'identity_relationships', ['relationship_type'], unique=False)
    op.create_index('idx_identity_rel_strength', 'identity_relationships', ['strength'], unique=False)

    # Create identity_history table
    op.create_table(
        'identity_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('node_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('node_type', sa.String(50), nullable=False),
        sa.Column('node_value', sa.String(255), nullable=False),
        sa.Column('old_confidence', sa.Float(), nullable=True),
        sa.Column('new_confidence', sa.Float(), nullable=True),
        sa.Column('confidence_delta', sa.Float(), nullable=True),
        sa.Column('change_reason', sa.String(255), nullable=True),
        sa.Column('triggering_memory_ids', postgresql.JSON(), default=[]),
        sa.Column('triggering_concept_ids', postgresql.JSON(), default=[]),
        sa.Column('event_type', sa.String(50), nullable=True),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['node_id'], ['identity_nodes.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_identity_history_user_id', 'identity_history', ['user_id'], unique=False)
    op.create_index('idx_identity_history_node_id', 'identity_history', ['node_id'], unique=False)
    op.create_index('idx_identity_history_created_at', 'identity_history', ['created_at'], unique=False)
    op.create_index('idx_identity_history_event_type', 'identity_history', ['event_type'], unique=False)


def downgrade() -> None:
    # Drop identity_history table
    op.drop_index('idx_identity_history_event_type', table_name='identity_history')
    op.drop_index('idx_identity_history_created_at', table_name='identity_history')
    op.drop_index('idx_identity_history_node_id', table_name='identity_history')
    op.drop_index('idx_identity_history_user_id', table_name='identity_history')
    op.drop_table('identity_history')

    # Drop identity_relationships table
    op.drop_index('idx_identity_rel_strength', table_name='identity_relationships')
    op.drop_index('idx_identity_rel_type', table_name='identity_relationships')
    op.drop_index('idx_identity_rel_target', table_name='identity_relationships')
    op.drop_index('idx_identity_rel_source', table_name='identity_relationships')
    op.drop_index('idx_identity_rel_user_id', table_name='identity_relationships')
    op.drop_table('identity_relationships')

    # Drop identity_nodes table
    op.drop_index('idx_identity_node_created_at', table_name='identity_nodes')
    op.drop_index('idx_identity_node_importance', table_name='identity_nodes')
    op.drop_index('idx_identity_node_confidence', table_name='identity_nodes')
    op.drop_index('idx_identity_node_value', table_name='identity_nodes')
    op.drop_index('idx_identity_node_type', table_name='identity_nodes')
    op.drop_index('idx_identity_node_user_id', table_name='identity_nodes')
    op.drop_table('identity_nodes')
