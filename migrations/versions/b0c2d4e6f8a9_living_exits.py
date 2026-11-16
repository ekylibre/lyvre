"""biens vivants immobilisés (lot AG5.c) : sorties (mort, sinistre, abattage), réinvestissements, dépréciations

Revision ID: b0c2d4e6f8a9
Revises: a9b1c3d5e7f8
Create Date: 2026-11-05 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b0c2d4e6f8a9'
down_revision = 'a9b1c3d5e7f8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'asset_living_exits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('on', sa.Date(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('units', sa.Integer(), nullable=True),
        sa.Column('price_cents', sa.Integer(), nullable=True),
        sa.Column('indemnity_cents', sa.Integer(), nullable=True),
        sa.Column('book_value_cents', sa.Integer(), nullable=False),
        sa.Column('entry_id', sa.Integer(), nullable=True),
        sa.Column('indemnity_entry_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], name='fk_asset_living_exits_asset_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entry_id'], ['journal_entries.id'], name='fk_asset_living_exits_entry_id', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['indemnity_entry_id'], ['journal_entries.id'], name='fk_asset_living_exits_indemnity_entry_id',
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_asset_living_exits_asset_id', 'asset_living_exits', ['asset_id'])
    op.create_table(
        'living_reinvestments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('exit_id', sa.Integer(), nullable=False),
        sa.Column('indemnity_cents', sa.Integer(), nullable=False),
        sa.Column('book_value_cents', sa.Integer(), nullable=False),
        sa.Column('deadline', sa.Date(), nullable=False),
        sa.Column('reinvested_cents', sa.Integer(), nullable=False),
        sa.Column('reinvested_on', sa.Date(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(['exit_id'], ['asset_living_exits.id'], name='fk_living_reinvestments_exit_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('exit_id', name='uq_living_reinvestments_exit_id'),
    )
    op.create_table(
        'asset_impairments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=300), nullable=True),
        sa.Column('entry_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], name='fk_asset_impairments_asset_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_asset_impairments_fiscal_year_id',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entry_id'], ['journal_entries.id'], name='fk_asset_impairments_entry_id', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', 'fiscal_year_id', name='uq_asset_impairments_asset_fy'),
    )
    op.create_index('ix_asset_impairments_asset_id', 'asset_impairments', ['asset_id'])


def downgrade():
    op.drop_index('ix_asset_impairments_asset_id', table_name='asset_impairments')
    op.drop_table('asset_impairments')
    op.drop_table('living_reinvestments')
    op.drop_index('ix_asset_living_exits_asset_id', table_name='asset_living_exits')
    op.drop_table('asset_living_exits')
