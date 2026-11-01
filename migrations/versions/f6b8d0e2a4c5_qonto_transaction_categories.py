"""catégories Qonto des transactions bancaires — lot TX1

Revision ID: f6b8d0e2a4c5
Revises: e5a7c9d1f3b4
Create Date: 2026-11-01 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6b8d0e2a4c5'
down_revision = 'e5a7c9d1f3b4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bank_transactions') as batch_op:
        batch_op.add_column(sa.Column('qonto_category', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('qonto_cashflow_category', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('qonto_cashflow_subcategory', sa.String(length=120), nullable=True))


def downgrade():
    with op.batch_alter_table('bank_transactions') as batch_op:
        batch_op.drop_column('qonto_cashflow_subcategory')
        batch_op.drop_column('qonto_cashflow_category')
        batch_op.drop_column('qonto_category')
