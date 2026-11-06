"""connecteur Ekylibre (lot AG11.c) : origine des clés de répartition

Revision ID: d0e2f4a6b8c0
Revises: c9d1e3f5a7b9
Create Date: 2026-11-07 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd0e2f4a6b8c0'
down_revision = 'c9d1e3f5a7b9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('analytic_keys') as batch:
        batch.add_column(sa.Column('source', sa.String(length=10), nullable=False, server_default='manual'))
        batch.add_column(sa.Column('synced_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('analytic_keys') as batch:
        batch.drop_column('synced_at')
        batch.drop_column('source')
