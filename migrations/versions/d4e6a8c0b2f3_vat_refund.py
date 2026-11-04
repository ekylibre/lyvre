"""remboursement de crédit de TVA demandé sur une déclaration (lot AG2.a, case 26 de la CA3, 3519)

Revision ID: d4e6a8c0b2f3
Revises: c3d5f7a9b1e2
Create Date: 2026-11-04 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e6a8c0b2f3'
down_revision = 'c3d5f7a9b1e2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('vat_returns') as batch_op:
        batch_op.add_column(sa.Column('refund_cents', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    with op.batch_alter_table('vat_returns') as batch_op:
        batch_op.drop_column('refund_cents')
