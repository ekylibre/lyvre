"""fonds dédiés (lot A.6) : ressources affectées et leurs dotations / utilisations

Revision ID: d5f3b8e1a426
Revises: c4e2a7d9b315
Create Date: 2026-10-23 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5f3b8e1a426'
down_revision = 'c4e2a7d9b315'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dedicated_funds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('resource_account_id', sa.Integer(), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('origin_fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['resource_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['origin_fiscal_year_id'], ['fiscal_years.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'dedicated_fund_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fund_id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('entry_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['fund_id'], ['dedicated_funds.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('dedicated_fund_movements', schema=None) as batch_op:
        batch_op.create_index('ix_dedicated_fund_movements_fund_id', ['fund_id'])
        batch_op.create_index('ix_dedicated_fund_movements_fiscal_year_id', ['fiscal_year_id'])


def downgrade():
    op.drop_table('dedicated_fund_movements')
    op.drop_table('dedicated_funds')
