"""inventaire de clôture agricole (lot AG4.b) : lots d'animaux et leurs mouvements

Revision ID: c5d7e9f1a3b4
Revises: b4c6d8e0f2a3
Create Date: 2026-11-05 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5d7e9f1a3b4'
down_revision = 'b4c6d8e0f2a3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'stock_lots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('species', sa.String(length=80), nullable=False),
        sa.Column('age_class', sa.String(length=80), nullable=True),
        sa.Column('destination', sa.String(length=12), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('average_weight_kg', sa.Numeric(10, 2), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name='fk_stock_lots_account_id', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'stock_lot_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lot_id', sa.Integer(), nullable=False),
        sa.Column('on', sa.Date(), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('heads', sa.Integer(), nullable=False),
        sa.Column('purchase_line_id', sa.Integer(), nullable=True),
        sa.Column('sale_id', sa.Integer(), nullable=True),
        sa.Column('counterpart_lot_id', sa.Integer(), nullable=True),
        sa.Column('pair_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['lot_id'], ['stock_lots.id'], name='fk_stock_lot_movements_lot_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['purchase_line_id'], ['purchase_lines.id'], name='fk_stock_lot_movements_purchase_line_id',
                                ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], name='fk_stock_lot_movements_sale_id', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['counterpart_lot_id'], ['stock_lots.id'], name='fk_stock_lot_movements_counterpart_lot_id',
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_stock_lot_movements_lot_id', 'stock_lot_movements', ['lot_id'])
    with op.batch_alter_table('stock_lines') as batch_op:
        batch_op.add_column(sa.Column('lot_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('heads', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('gap_reason', sa.String(length=300), nullable=True))
        batch_op.create_foreign_key('fk_stock_lines_lot_id', 'stock_lots', ['lot_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_stock_lines_lot_id', ['lot_id'])


def downgrade():
    with op.batch_alter_table('stock_lines') as batch_op:
        batch_op.drop_index('ix_stock_lines_lot_id')
        batch_op.drop_constraint('fk_stock_lines_lot_id', type_='foreignkey')
        batch_op.drop_column('gap_reason')
        batch_op.drop_column('heads')
        batch_op.drop_column('lot_id')
    op.drop_index('ix_stock_lot_movements_lot_id', table_name='stock_lot_movements')
    op.drop_table('stock_lot_movements')
    op.drop_table('stock_lots')
