"""lot F4 : période de service des factures d'achat et des lignes d'écriture (CCA / PCA)

Revision ID: e4a6b8c0d2f4
Revises: d3f5a7b9c1e3
Create Date: 2026-10-24 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4a6b8c0d2f4'
down_revision = 'd3f5a7b9c1e3'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('purchases', 'journal_lines'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('service_start', sa.Date(), nullable=True))
            batch_op.add_column(sa.Column('service_end', sa.Date(), nullable=True))


def downgrade():
    for table in ('journal_lines', 'purchases'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_column('service_end')
            batch_op.drop_column('service_start')
