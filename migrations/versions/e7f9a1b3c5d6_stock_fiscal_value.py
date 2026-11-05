"""inventaire de clôture agricole (lot AG4.e) : valeur fiscale des lignes de stock

Revision ID: e7f9a1b3c5d6
Revises: d6e8f0a2b4c5
Create Date: 2026-11-05 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7f9a1b3c5d6'
down_revision = 'd6e8f0a2b4c5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('stock_lines') as batch_op:
        batch_op.add_column(sa.Column('fiscal_method', sa.String(length=8), nullable=False, server_default='none'))
        batch_op.add_column(sa.Column('fiscal_value_cents', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('fiscal_reason', sa.String(length=300), nullable=True))


def downgrade():
    with op.batch_alter_table('stock_lines') as batch_op:
        batch_op.drop_column('fiscal_reason')
        batch_op.drop_column('fiscal_value_cents')
        batch_op.drop_column('fiscal_method')
