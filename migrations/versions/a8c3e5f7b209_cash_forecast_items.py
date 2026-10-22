"""prévisionnel de trésorerie (lot C.4) : saisies manuelles, avec répétition mensuelle

Revision ID: a8c3e5f7b209
Revises: f2b6d8a3c147
Create Date: 2026-10-23 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8c3e5f7b209'
down_revision = 'f2b6d8a3c147'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cash_forecast_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('bank_account_id', sa.Integer(), nullable=True),
        sa.Column('repeat_monthly_until', sa.Date(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('cash_forecast_items')
