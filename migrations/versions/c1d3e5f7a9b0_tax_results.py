"""fiscalité BA (lot AG6.a) : résultat fiscal, lignes de passage saisies, associés exploitants

Revision ID: c1d3e5f7a9b0
Revises: b0c2d4e6f8a9
Create Date: 2026-11-05 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1d3e5f7a9b0'
down_revision = 'b0c2d4e6f8a9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tax_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('snapshot_json', sa.Text(), nullable=True),
        sa.Column('frozen_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_tax_results_fiscal_year_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fiscal_year_id', name='uq_tax_results_fiscal_year_id'),
    )
    op.create_table(
        'tax_result_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_tax_result_lines_fiscal_year_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tax_result_lines_fiscal_year_id', 'tax_result_lines', ['fiscal_year_id'])
    with op.batch_alter_table('associates') as batch_op:
        batch_op.add_column(sa.Column('is_operator', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('young_farmer_since', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('profit_share_bp', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('associates') as batch_op:
        batch_op.drop_column('profit_share_bp')
        batch_op.drop_column('young_farmer_since')
        batch_op.drop_column('is_operator')
    op.drop_index('ix_tax_result_lines_fiscal_year_id', table_name='tax_result_lines')
    op.drop_table('tax_result_lines')
    op.drop_table('tax_results')
