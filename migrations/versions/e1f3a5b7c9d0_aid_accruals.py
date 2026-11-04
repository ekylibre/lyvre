"""aides PAC et subventions (lot AG3.c) : décisions de clôture (produits à recevoir des aides)

Revision ID: e1f3a5b7c9d0
Revises: d0e2f4a6b8c9
Create Date: 2026-11-05 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1f3a5b7c9d0'
down_revision = 'd0e2f4a6b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'aid_accruals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('aid_id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('proposed_cents', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['aid_id'], ['aids.id'], name='fk_aid_accruals_aid_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_aid_accruals_fiscal_year_id',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], name='fk_aid_accruals_journal_entry_id',
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('aid_id', 'fiscal_year_id', name='uq_aid_accruals_aid_fy'),
    )
    op.create_index('ix_aid_accruals_aid_id', 'aid_accruals', ['aid_id'])


def downgrade():
    op.drop_index('ix_aid_accruals_aid_id', table_name='aid_accruals')
    op.drop_table('aid_accruals')
