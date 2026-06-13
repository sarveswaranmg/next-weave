"""Initial migration"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers used by Alembic
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('external_id', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_id'),
        sa.UniqueConstraint('email'),
    )
    op.create_index('idx_user_external_id', 'users', ['external_id'])

    # Create sessions table
    op.create_table(
        'sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_token', sa.String(255), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('ended_at', sa.DateTime(), nullable=True),
        sa.Column('metadata', postgresql.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_token'),
    )
    op.create_index('idx_session_user_id', 'sessions', ['user_id'])
    op.create_index('idx_session_token', 'sessions', ['session_token'])

    # Create memories table
    op.create_table(
        'memories',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('memory_type', sa.Enum('episodic', 'semantic', 'identity', 'procedural', name='memorytypeenum'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('importance_score', sa.Float(), nullable=False),
        sa.Column('embedding', sa.String(255), nullable=True),
        sa.Column('metadata', postgresql.JSON(), nullable=False),
        sa.Column('reinforcement_count', sa.Integer(), nullable=False),
        sa.Column('access_count', sa.Integer(), nullable=False),
        sa.Column('last_accessed', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_memory_user_id', 'memories', ['user_id'])
    op.create_index('idx_memory_type', 'memories', ['memory_type'])
    op.create_index('idx_memory_importance', 'memories', ['importance_score'])
    op.create_index('idx_memory_created_at', 'memories', ['created_at'])
    op.create_index('idx_memory_last_accessed', 'memories', ['last_accessed'])

    # Create memory embeddings table
    op.create_table(
        'memory_embeddings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('memory_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('embedding', sa.String(), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['memory_id'], ['memories.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_embedding_memory_id', 'memory_embeddings', ['memory_id'])
    op.create_index('idx_embedding_model', 'memory_embeddings', ['model'])

    # Create retrieval logs table
    op.create_table(
        'retrieval_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('query', sa.Text(), nullable=True),
        sa.Column('retrieved_memory_ids', postgresql.JSON(), nullable=True),
        sa.Column('retrieval_latency_ms', sa.Float(), nullable=True),
        sa.Column('context_token_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_retrieval_user_id', 'retrieval_logs', ['user_id'])
    op.create_index('idx_retrieval_created_at', 'retrieval_logs', ['created_at'])

    # Create memory consolidations table
    op.create_table(
        'memory_consolidations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_memory_ids', postgresql.JSON(), nullable=True),
        sa.Column('consolidated_memory_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('consolidation_score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['consolidated_memory_id'], ['memories.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_consolidation_user_id', 'memory_consolidations', ['user_id'])
    op.create_index('idx_consolidation_memory_id', 'memory_consolidations', ['consolidated_memory_id'])


def downgrade() -> None:
    op.drop_index('idx_consolidation_memory_id', table_name='memory_consolidations')
    op.drop_index('idx_consolidation_user_id', table_name='memory_consolidations')
    op.drop_table('memory_consolidations')
    op.drop_index('idx_retrieval_created_at', table_name='retrieval_logs')
    op.drop_index('idx_retrieval_user_id', table_name='retrieval_logs')
    op.drop_table('retrieval_logs')
    op.drop_index('idx_embedding_model', table_name='memory_embeddings')
    op.drop_index('idx_embedding_memory_id', table_name='memory_embeddings')
    op.drop_table('memory_embeddings')
    op.drop_index('idx_memory_last_accessed', table_name='memories')
    op.drop_index('idx_memory_created_at', table_name='memories')
    op.drop_index('idx_memory_importance', table_name='memories')
    op.drop_index('idx_memory_type', table_name='memories')
    op.drop_index('idx_memory_user_id', table_name='memories')
    op.drop_table('memories')
    op.drop_index('idx_session_token', table_name='sessions')
    op.drop_index('idx_session_user_id', table_name='sessions')
    op.drop_table('sessions')
    op.drop_index('idx_user_external_id', table_name='users')
    op.drop_table('users')
