"""Day 9: World Model Engine.

Adds world_entities, world_relationships, projects, and architectural_decisions.

Revision ID: 009
Revises: 008
Create Date: 2026-07-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None

WORLD_ENTITY_TYPES = [
    'PERSON', 'PROJECT', 'COMPANY', 'GOAL', 'TECHNOLOGY', 'FILE', 'REPOSITORY',
    'TASK', 'MEETING', 'IDEA', 'DOCUMENT', 'API', 'LOCATION', 'DEVICE', 'SERVICE',
]
PROJECT_STATUSES = ['ACTIVE', 'PAUSED', 'COMPLETED', 'ARCHIVED']


def upgrade() -> None:
    world_entity_type_enum = postgresql.ENUM(*WORLD_ENTITY_TYPES, name='worldentitytypeenum')
    world_entity_type_enum.create(op.get_bind(), checkfirst=True)

    project_status_enum = postgresql.ENUM(*PROJECT_STATUSES, name='projectstatusenum')
    project_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        'world_entities',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('entity_type', sa.Enum(*WORLD_ENTITY_TYPES, name='worldentitytypeenum'), nullable=False),
        sa.Column('entity_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('confidence', sa.Float(), server_default='0.5'),
        sa.Column('mention_count', sa.Integer(), server_default='1'),
        sa.Column('attributes', postgresql.JSON(), default={}),
        sa.Column('supporting_memory_ids', postgresql.JSON(), default=[]),
        sa.Column('first_seen_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('last_seen_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_world_entity_user_id', 'world_entities', ['user_id'], unique=False)
    op.create_index('idx_world_entity_type', 'world_entities', ['entity_type'], unique=False)
    op.create_index('idx_world_entity_name', 'world_entities', ['entity_name'], unique=False)
    op.create_index('idx_world_entity_confidence', 'world_entities', ['confidence'], unique=False)
    op.create_index('idx_world_entity_last_seen', 'world_entities', ['last_seen_at'], unique=False)

    op.create_table(
        'world_relationships',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_entity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('relationship_type', sa.String(50), nullable=False),
        sa.Column('strength', sa.Float(), server_default='0.5'),
        sa.Column('evidence_count', sa.Integer(), server_default='1'),
        sa.Column('supporting_memory_ids', postgresql.JSON(), default=[]),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['source_entity_id'], ['world_entities.id'], ),
        sa.ForeignKeyConstraint(['target_entity_id'], ['world_entities.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_world_rel_user_id', 'world_relationships', ['user_id'], unique=False)
    op.create_index('idx_world_rel_source', 'world_relationships', ['source_entity_id'], unique=False)
    op.create_index('idx_world_rel_target', 'world_relationships', ['target_entity_id'], unique=False)
    op.create_index('idx_world_rel_type', 'world_relationships', ['relationship_type'], unique=False)
    op.create_index('idx_world_rel_strength', 'world_relationships', ['strength'], unique=False)

    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('world_entity_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('project_name', sa.String(255), nullable=False),
        sa.Column('status', sa.Enum(*PROJECT_STATUSES, name='projectstatusenum'), server_default='ACTIVE'),
        sa.Column('current_phase', sa.String(255), nullable=True),
        sa.Column('progress', sa.Float(), server_default='0.0'),
        sa.Column('next_step', sa.Text(), nullable=True),
        sa.Column('goals', postgresql.JSON(), default=[]),
        sa.Column('architecture_notes', sa.Text(), nullable=True),
        sa.Column('tech_stack', postgresql.JSON(), default=[]),
        sa.Column('dependencies', postgresql.JSON(), default=[]),
        sa.Column('roadmap', postgresql.JSON(), default=[]),
        sa.Column('open_questions', postgresql.JSON(), default=[]),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['world_entity_id'], ['world_entities.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_project_user_id', 'projects', ['user_id'], unique=False)
    op.create_index('idx_project_name', 'projects', ['project_name'], unique=False)
    op.create_index('idx_project_status', 'projects', ['status'], unique=False)
    op.create_index('idx_project_updated_at', 'projects', ['updated_at'], unique=False)

    op.create_table(
        'architectural_decisions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('decision', sa.Text(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('impact', sa.Text(), nullable=True),
        sa.Column('status', sa.String(50), server_default='decided'),
        sa.Column('confidence', sa.Float(), server_default='0.7'),
        sa.Column('supporting_memory_ids', postgresql.JSON(), default=[]),
        sa.Column('metadata', postgresql.JSON(), default={}),
        sa.Column('timestamp', sa.DateTime(), default=sa.func.now()),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_decision_user_id', 'architectural_decisions', ['user_id'], unique=False)
    op.create_index('idx_decision_project_id', 'architectural_decisions', ['project_id'], unique=False)
    op.create_index('idx_decision_timestamp', 'architectural_decisions', ['timestamp'], unique=False)
    op.create_index('idx_decision_status', 'architectural_decisions', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_decision_status', table_name='architectural_decisions')
    op.drop_index('idx_decision_timestamp', table_name='architectural_decisions')
    op.drop_index('idx_decision_project_id', table_name='architectural_decisions')
    op.drop_index('idx_decision_user_id', table_name='architectural_decisions')
    op.drop_table('architectural_decisions')

    op.drop_index('idx_project_updated_at', table_name='projects')
    op.drop_index('idx_project_status', table_name='projects')
    op.drop_index('idx_project_name', table_name='projects')
    op.drop_index('idx_project_user_id', table_name='projects')
    op.drop_table('projects')

    op.drop_index('idx_world_rel_strength', table_name='world_relationships')
    op.drop_index('idx_world_rel_type', table_name='world_relationships')
    op.drop_index('idx_world_rel_target', table_name='world_relationships')
    op.drop_index('idx_world_rel_source', table_name='world_relationships')
    op.drop_index('idx_world_rel_user_id', table_name='world_relationships')
    op.drop_table('world_relationships')

    op.drop_index('idx_world_entity_last_seen', table_name='world_entities')
    op.drop_index('idx_world_entity_confidence', table_name='world_entities')
    op.drop_index('idx_world_entity_name', table_name='world_entities')
    op.drop_index('idx_world_entity_type', table_name='world_entities')
    op.drop_index('idx_world_entity_user_id', table_name='world_entities')
    op.drop_table('world_entities')

    postgresql.ENUM(name='projectstatusenum').drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name='worldentitytypeenum').drop(op.get_bind(), checkfirst=True)
