"""assistant Claude (lot AG9b.a) : conversations, messages, propositions

Revision ID: c3d5e7f9a1b3
Revises: b2c4d6e8f0a2
Create Date: 2026-11-06 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d5e7f9a1b3'
down_revision = 'b2c4d6e8f0a2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'assistant_conversations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_assistant_conversations_fiscal_year_id', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('assistant_conversations') as batch:
        batch.create_index('ix_assistant_conversations_user_id', ['user_id'])
    op.create_table(
        'assistant_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conversation_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=10), nullable=False),
        sa.Column('content_json', sa.Text(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False, server_default='text'),
        sa.Column('model', sa.String(length=40), nullable=True),
        sa.Column('stop_reason', sa.String(length=20), nullable=True),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cache_read_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cache_creation_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['assistant_conversations.id'], name='fk_assistant_messages_conversation_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('assistant_messages') as batch:
        batch.create_index('ix_assistant_messages_conversation_id', ['conversation_id'])
        batch.create_index('ix_assistant_messages_created_at', ['created_at'])
    op.create_table(
        'assistant_proposals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('message_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='open'),
        sa.Column('result_ref', sa.String(length=60), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['assistant_messages.id'], name='fk_assistant_proposals_message_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('assistant_proposals') as batch:
        batch.create_index('ix_assistant_proposals_message_id', ['message_id'])


def downgrade():
    with op.batch_alter_table('assistant_proposals') as batch:
        batch.drop_index('ix_assistant_proposals_message_id')
    op.drop_table('assistant_proposals')
    with op.batch_alter_table('assistant_messages') as batch:
        batch.drop_index('ix_assistant_messages_created_at')
        batch.drop_index('ix_assistant_messages_conversation_id')
    op.drop_table('assistant_messages')
    with op.batch_alter_table('assistant_conversations') as batch:
        batch.drop_index('ix_assistant_conversations_user_id')
    op.drop_table('assistant_conversations')
