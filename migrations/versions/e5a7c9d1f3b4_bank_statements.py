"""relevés de compte mensuels (PDF, Qonto ou dépôt) — lot RQ1

Revision ID: e5a7c9d1f3b4
Revises: d4f6b8c0e2a3
Create Date: 2026-11-01 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5a7c9d1f3b4'
down_revision = 'd4f6b8c0e2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bank_statements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=False),
        sa.Column('period', sa.Date(), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False, server_default='qonto'),
        sa.Column('qonto_id', sa.String(length=36), nullable=True),
        sa.Column('file_path', sa.String(length=255), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.Column('replaced_at', sa.DateTime(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('bank_account_id', 'period', name='uq_bank_statements_period'),
    )
    op.create_index('ix_bank_statements_bank_account_id', 'bank_statements', ['bank_account_id'])


def downgrade():
    op.drop_index('ix_bank_statements_bank_account_id', table_name='bank_statements')
    op.drop_table('bank_statements')
