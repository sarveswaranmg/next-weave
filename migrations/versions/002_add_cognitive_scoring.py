"""Add cognitive scoring dimensions to memories table (Day 2)

Revision ID: 002_add_cognitive_scoring
Revises: 001
Create Date: 2026-05-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '002_add_cognitive_scoring'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade: Add cognitive scoring dimensions to memories"""
    
    # Create the CognitiveMemoryStateEnum type
    cognitive_state_enum = postgresql.ENUM(
        'ACTIVE',
        'REINFORCED', 
        'SEMANTIC_CANDIDATE',
        'DORMANT',
        'DECAYING',
        'ARCHIVED',
        name='cognitivememorystateenum', create_type=False,
    )
    cognitive_state_enum.create(op.get_bind(), checkfirst=True)
    
    # Add cognitive scoring columns
    op.add_column('memories', sa.Column('future_utility_score', sa.Float(), nullable=True, server_default='0.5'))
    op.add_column('memories', sa.Column('identity_impact_score', sa.Float(), nullable=True, server_default='0.5'))
    op.add_column('memories', sa.Column('emotional_salience_score', sa.Float(), nullable=True, server_default='0.5'))
    op.add_column('memories', sa.Column('reinforcement_score', sa.Float(), nullable=True, server_default='0.5'))
    op.add_column('memories', sa.Column('temporal_persistence_score', sa.Float(), nullable=True, server_default='0.5'))
    
    # Add cognitive state and strength
    op.add_column('memories', sa.Column('cognitive_state', cognitive_state_enum, nullable=True, server_default='ACTIVE'))
    op.add_column('memories', sa.Column('memory_strength', sa.Float(), nullable=True, server_default='0.5'))
    op.add_column('memories', sa.Column('decay_rate', sa.Float(), nullable=True, server_default='0.05'))
    
    # Add reinforcement tracking
    op.add_column('memories', sa.Column('retrieval_count', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('memories', sa.Column('last_reinforced_at', sa.DateTime(), nullable=True))
    
    # Create indexes for performance
    op.create_index('idx_memory_cognitive_state', 'memories', ['cognitive_state'])
    op.create_index('idx_memory_memory_strength', 'memories', ['memory_strength'])
    op.create_index('idx_memory_last_reinforced', 'memories', ['last_reinforced_at'])
    op.create_index('idx_memory_future_utility', 'memories', ['future_utility_score'])
    op.create_index('idx_memory_identity_impact', 'memories', ['identity_impact_score'])
    op.create_index('idx_memory_emotional_salience', 'memories', ['emotional_salience_score'])


def downgrade() -> None:
    """Downgrade: Remove cognitive scoring dimensions from memories"""
    
    # Drop indexes
    op.drop_index('idx_memory_emotional_salience', table_name='memories')
    op.drop_index('idx_memory_identity_impact', table_name='memories')
    op.drop_index('idx_memory_future_utility', table_name='memories')
    op.drop_index('idx_memory_last_reinforced', table_name='memories')
    op.drop_index('idx_memory_memory_strength', table_name='memories')
    op.drop_index('idx_memory_cognitive_state', table_name='memories')
    
    # Drop columns
    op.drop_column('memories', 'last_reinforced_at')
    op.drop_column('memories', 'retrieval_count')
    op.drop_column('memories', 'decay_rate')
    op.drop_column('memories', 'memory_strength')
    op.drop_column('memories', 'cognitive_state')
    op.drop_column('memories', 'temporal_persistence_score')
    op.drop_column('memories', 'reinforcement_score')
    op.drop_column('memories', 'emotional_salience_score')
    op.drop_column('memories', 'identity_impact_score')
    op.drop_column('memories', 'future_utility_score')
    
    # Drop enum type
    cognitive_state_enum = postgresql.ENUM(
        'ACTIVE',
        'REINFORCED',
        'SEMANTIC_CANDIDATE',
        'DORMANT',
        'DECAYING',
        'ARCHIVED',
        name='cognitivememorystateenum'
    )
    cognitive_state_enum.drop(op.get_bind(), checkfirst=True)
