"""caisse (lot D.1) : nature des comptes de trésorerie (banque ou caisse)

Revision ID: e5a9c3d7f106
Revises: d3f7b9c1e504
Create Date: 2026-10-25 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5a9c3d7f106'
down_revision = 'd3f7b9c1e504'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bank_accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kind', sa.String(length=8), server_default='bank', nullable=False))


def downgrade():
    with op.batch_alter_table('bank_accounts', schema=None) as batch_op:
        batch_op.drop_column('kind')
