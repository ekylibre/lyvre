"""biens vivants immobilisés (lot AG5.b) : coûts de croissance en cours, lien du mouvement de stock vers sa fiche

Revision ID: a9b1c3d5e7f8
Revises: f8a0b2c4d6e7
Create Date: 2026-11-05 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a9b1c3d5e7f8'
down_revision = 'f8a0b2c4d6e7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'living_wip_costs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('basis', sa.String(length=300), nullable=True),
        sa.Column('entry_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], name='fk_living_wip_costs_asset_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_living_wip_costs_fiscal_year_id',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entry_id'], ['journal_entries.id'], name='fk_living_wip_costs_entry_id', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', 'fiscal_year_id', name='uq_living_wip_costs_asset_fy'),
    )
    op.create_index('ix_living_wip_costs_asset_id', 'living_wip_costs', ['asset_id'])
    with op.batch_alter_table('stock_lot_movements') as batch_op:
        batch_op.add_column(sa.Column('asset_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_stock_lot_movements_asset_id', 'assets', ['asset_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('stock_lot_movements') as batch_op:
        batch_op.drop_constraint('fk_stock_lot_movements_asset_id', type_='foreignkey')
        batch_op.drop_column('asset_id')
    op.drop_index('ix_living_wip_costs_asset_id', table_name='living_wip_costs')
    op.drop_table('living_wip_costs')
