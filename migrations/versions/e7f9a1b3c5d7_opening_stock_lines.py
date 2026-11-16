"""stock d'entrée au passage du micro-BA au réel (lot CG5.c)

Revision ID: e7f9a1b3c5d7
Revises: d6e8f0a2b4c6
Create Date: 2026-11-08 04:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f9a1b3c5d7'
down_revision = 'd6e8f0a2b4c6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'opening_stock_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('quantity', sa.Numeric(14, 3), nullable=False),
        sa.Column('unit', sa.String(length=10), nullable=False),
        sa.Column('method', sa.String(length=22), nullable=False),
        sa.Column('cost_unit_cents', sa.Integer(), nullable=True),
        sa.Column('market_unit_cents', sa.Integer(), nullable=True),
        sa.Column('amount_cents', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_opening_stock_lines_fiscal_year_id', 'opening_stock_lines', ['fiscal_year_id'])


def downgrade():
    op.drop_index('ix_opening_stock_lines_fiscal_year_id', table_name='opening_stock_lines')
    op.drop_table('opening_stock_lines')
