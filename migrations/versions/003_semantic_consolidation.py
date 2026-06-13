"""Day 3: Semantic Consolidation Engine - Add concept, cluster, and relationship tables.

Revision ID: 003
Revises: 002_add_cognitive_scoring
Create Date: 2026-06-08 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002_add_cognitive_scoring'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create concept_memories table
    op.create_table(
        'concept_memories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('concept_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), default=0.0),
        sa.Column('support_count', sa.Integer(), default=1),
        sa.Column('supporting_memory_ids', postgresql.JSON(), default=[]),
        sa.Column('related_concept_ids', postgresql.JSON(), default=[]),
        sa.Column('is_derived_from', sa.String(255), nullable=True),
        sa.Column('last_reinforced_at', sa.DateTime(), nullable=True),
        sa.Column('reinforcement_count', sa.Integer(), default=0),
        sa.Column('embedding', sa.String(255), nullable=True),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_concept_user_id', 'concept_memories', ['user_id'], unique=False)
    op.create_index('idx_concept_name', 'concept_memories', ['concept_name'], unique=False)
    op.create_index('idx_concept_confidence', 'concept_memories', ['confidence'], unique=False)
    op.create_index('idx_concept_created_at', 'concept_memories', ['created_at'], unique=False)

    # Create memory_clusters table
    op.create_table(
        'memory_clusters',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('cluster_id', sa.String(255), nullable=False),
        sa.Column('theme', sa.String(255), nullable=True),
        sa.Column('memory_ids', postgresql.JSON(), default=[]),
        sa.Column('member_count', sa.Integer(), default=0),
        sa.Column('avg_similarity', sa.Float(), default=0.0),
        sa.Column('confidence', sa.Float(), default=0.0),
        sa.Column('centroid_embedding', sa.String(255), nullable=True),
        sa.Column('consolidation_status', sa.String(50), default='pending'),
        sa.Column('concept_generated', sa.String(255), nullable=True),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_cluster_user_id', 'memory_clusters', ['user_id'], unique=False)
    op.create_index('idx_cluster_theme', 'memory_clusters', ['theme'], unique=False)
    op.create_index('idx_cluster_status', 'memory_clusters', ['consolidation_status'], unique=False)
    op.create_index('idx_cluster_created_at', 'memory_clusters', ['created_at'], unique=False)

    # Create concept_relationships table
    op.create_table(
        'concept_relationships',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_concept_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_concept_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('relationship_type', sa.String(50), nullable=False),
        sa.Column('strength', sa.Float(), default=0.5),
        sa.Column('reinforcement_count', sa.Integer(), default=1),
        sa.Column('last_reinforced_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['source_concept_id'], ['concept_memories.id'], ),
        sa.ForeignKeyConstraint(['target_concept_id'], ['concept_memories.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_relationship_user_id', 'concept_relationships', ['user_id'], unique=False)
    op.create_index('idx_relationship_source', 'concept_relationships', ['source_concept_id'], unique=False)
    op.create_index('idx_relationship_target', 'concept_relationships', ['target_concept_id'], unique=False)
    op.create_index('idx_relationship_type', 'concept_relationships', ['relationship_type'], unique=False)
    op.create_index('idx_relationship_strength', 'concept_relationships', ['strength'], unique=False)

    # Create consolidation_metrics table
    op.create_table(
        'consolidation_metrics',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('consolidation_run_id', sa.String(255), nullable=True),
        sa.Column('consolidation_timestamp', sa.DateTime(), default=sa.func.now()),
        sa.Column('total_memories', sa.Integer(), default=0),
        sa.Column('episodic_memories', sa.Integer(), default=0),
        sa.Column('semantic_memories', sa.Integer(), default=0),
        sa.Column('identity_memories', sa.Integer(), default=0),
        sa.Column('procedural_memories', sa.Integer(), default=0),
        sa.Column('cluster_count', sa.Integer(), default=0),
        sa.Column('avg_cluster_size', sa.Float(), default=0.0),
        sa.Column('concept_count', sa.Integer(), default=0),
        sa.Column('new_concepts_created', sa.Integer(), default=0),
        sa.Column('concepts_reinforced', sa.Integer(), default=0),
        sa.Column('total_relationships', sa.Integer(), default=0),
        sa.Column('avg_concept_degree', sa.Float(), default=0.0),
        sa.Column('memory_reduction_percentage', sa.Float(), default=0.0),
        sa.Column('compression_ratio', sa.Float(), default=0.0),
        sa.Column('token_reduction', sa.Integer(), default=0),
        sa.Column('processing_time_ms', sa.Float(), default=0.0),
        sa.Column('avg_concept_confidence', sa.Float(), default=0.0),
        sa.Column('min_cluster_similarity', sa.Float(), default=0.0),
        sa.Column('max_cluster_similarity', sa.Float(), default=0.0),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_metrics_user_id', 'consolidation_metrics', ['user_id'], unique=False)
    op.create_index('idx_metrics_timestamp', 'consolidation_metrics', ['consolidation_timestamp'], unique=False)
    op.create_index('idx_metrics_run_id', 'consolidation_metrics', ['consolidation_run_id'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_metrics_run_id', table_name='consolidation_metrics')
    op.drop_index('idx_metrics_timestamp', table_name='consolidation_metrics')
    op.drop_index('idx_metrics_user_id', table_name='consolidation_metrics')
    op.drop_table('consolidation_metrics')
    
    op.drop_index('idx_relationship_strength', table_name='concept_relationships')
    op.drop_index('idx_relationship_type', table_name='concept_relationships')
    op.drop_index('idx_relationship_target', table_name='concept_relationships')
    op.drop_index('idx_relationship_source', table_name='concept_relationships')
    op.drop_index('idx_relationship_user_id', table_name='concept_relationships')
    op.drop_table('concept_relationships')
    
    op.drop_index('idx_cluster_created_at', table_name='memory_clusters')
    op.drop_index('idx_cluster_status', table_name='memory_clusters')
    op.drop_index('idx_cluster_theme', table_name='memory_clusters')
    op.drop_index('idx_cluster_user_id', table_name='memory_clusters')
    op.drop_table('memory_clusters')
    
    op.drop_index('idx_concept_created_at', table_name='concept_memories')
    op.drop_index('idx_concept_confidence', table_name='concept_memories')
    op.drop_index('idx_concept_name', table_name='concept_memories')
    op.drop_index('idx_concept_user_id', table_name='concept_memories')
    op.drop_table('concept_memories')
