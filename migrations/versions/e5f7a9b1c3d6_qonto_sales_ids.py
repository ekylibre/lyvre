"""module Ventes (lot S4) : identifiants Qonto des clients et des produits

Revision ID: e5f7a9b1c3d6
Revises: d4e6f8a0b2c5
Create Date: 2026-10-24 01:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f7a9b1c3d6'
down_revision = 'd4e6f8a0b2c5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.add_column(sa.Column('qonto_client_id', sa.String(length=36), nullable=True))
        batch_op.create_index('ix_entities_qonto_client_id', ['qonto_client_id'])
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('qonto_product_id', sa.String(length=36), nullable=True))


def downgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('qonto_product_id')
    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.drop_index('ix_entities_qonto_client_id')
        batch_op.drop_column('qonto_client_id')
