"""fiscalité BA (lot AG6.e) : historique des années antérieures, étalement 75-0 A, produits repérés (accessoires, façon)

Revision ID: f4a6b8c0d2e4
Revises: e3f5a7b9c1d2
Create Date: 2026-11-05 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4a6b8c0d2e4'
down_revision = 'e3f5a7b9c1d2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ba_history_years',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('agricultural_receipts_cents', sa.BigInteger(), nullable=True),
        sa.Column('accessory_receipts_cents', sa.BigInteger(), nullable=True),
        sa.Column('fiscal_result_cents', sa.BigInteger(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year', name='uq_ba_history_years_year'),
    )
    op.create_table(
        'income_spreads',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('amount_cents', sa.BigInteger(), nullable=False),
        sa.Column('reason', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_income_spreads_fiscal_year_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('income_spreads') as batch:
        batch.create_index('ix_income_spreads_fiscal_year_id', ['fiscal_year_id'])
    with op.batch_alter_table('accounts') as batch:
        batch.add_column(sa.Column('ba_income_class', sa.String(length=12), nullable=True))


def downgrade():
    with op.batch_alter_table('accounts') as batch:
        batch.drop_column('ba_income_class')
    with op.batch_alter_table('income_spreads') as batch:
        batch.drop_index('ix_income_spreads_fiscal_year_id')
    op.drop_table('income_spreads')
    op.drop_table('ba_history_years')
