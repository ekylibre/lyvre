"""fiscalité BA (lot AG6.g) : choix des plus-values (151 septies) et crédits d'impôt

Revision ID: a5b7c9d1e3f5
Revises: f4a6b8c0d2e4
Create Date: 2026-11-05 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a5b7c9d1e3f5'
down_revision = 'f4a6b8c0d2e4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'capital_gain_choices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('apply_151_septies', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('activity_since', sa.Date(), nullable=True),
        sa.Column('young_farmer_buyer', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_capital_gain_choices_fiscal_year_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fiscal_year_id', name='uq_capital_gain_choices_fiscal_year_id'),
    )
    op.create_table(
        'tax_credits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('data_json', sa.Text(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_tax_credits_fiscal_year_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fiscal_year_id', 'kind', name='uq_tax_credits_fiscal_year_kind'),
    )
    with op.batch_alter_table('tax_credits') as batch:
        batch.create_index('ix_tax_credits_fiscal_year_id', ['fiscal_year_id'])


def downgrade():
    with op.batch_alter_table('tax_credits') as batch:
        batch.drop_index('ix_tax_credits_fiscal_year_id')
    op.drop_table('tax_credits')
    op.drop_table('capital_gain_choices')
