"""échéancier de l'exploitation (lot AG9a.b) : états des occurrences (faite, ignorée)

Revision ID: b8c0e2a4f6d7
Revises: a7b9d1f3e5c6
Create Date: 2026-11-04 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8c0e2a4f6d7'
down_revision = 'a7b9d1f3e5c6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'deadline_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('deadline_id', sa.String(length=20), nullable=False),
        sa.Column('occurs_on', sa.Date(), nullable=False),
        sa.Column('period', sa.String(length=60), nullable=False, server_default=''),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('done_on', sa.Date(), nullable=True),
        sa.Column('origin', sa.String(length=12), nullable=False, server_default='manual'),
        sa.Column('bank_transaction_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['bank_transaction_id'], ['bank_transactions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('deadline_id', 'occurs_on', 'period', name='uq_deadline_states_occurrence'),
    )
    op.create_index('ix_deadline_states_deadline_id', 'deadline_states', ['deadline_id'])


def downgrade():
    op.drop_index('ix_deadline_states_deadline_id', table_name='deadline_states')
    op.drop_table('deadline_states')
