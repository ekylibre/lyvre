"""fiscalité BA (lot AG6.c) : DEP (déductions, mouvements, substituts d'épargne), compte bancaire d'épargne DEP

Revision ID: d2e4f6a8b0c1
Revises: c1d3e5f7a9b0
Create Date: 2026-11-05 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2e4f6a8b0c1'
down_revision = 'c1d3e5f7a9b0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dep_entries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=4), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=True),
        sa.Column('origin_year', sa.Integer(), nullable=True),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_dep_entries_fiscal_year_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fiscal_year_id', name='uq_dep_entries_fiscal_year_id'),
    )
    op.create_table(
        'dep_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entry_id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=14), nullable=False),
        sa.Column('on', sa.Date(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('hazard', sa.String(length=10), nullable=True),
        sa.Column('exempt_cents', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(['entry_id'], ['dep_entries.id'], name='fk_dep_movements_entry_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_dep_movements_fiscal_year_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_dep_movements_entry_id', 'dep_movements', ['entry_id'])
    op.create_index('ix_dep_movements_fiscal_year_id', 'dep_movements', ['fiscal_year_id'])
    op.create_table(
        'dep_substitutes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_dep_substitutes_fiscal_year_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_dep_substitutes_fiscal_year_id', 'dep_substitutes', ['fiscal_year_id'])
    with op.batch_alter_table('bank_accounts') as batch_op:
        batch_op.add_column(sa.Column('dep_savings', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('bank_accounts') as batch_op:
        batch_op.drop_column('dep_savings')
    op.drop_index('ix_dep_substitutes_fiscal_year_id', table_name='dep_substitutes')
    op.drop_table('dep_substitutes')
    op.drop_index('ix_dep_movements_fiscal_year_id', table_name='dep_movements')
    op.drop_index('ix_dep_movements_entry_id', table_name='dep_movements')
    op.drop_table('dep_movements')
    op.drop_table('dep_entries')
