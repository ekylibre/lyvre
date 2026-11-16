"""autofactures reçues (lot AG10.c) : colonnes de cycle de vie, numéro unique par client

Revision ID: e5f7a9b1c3d5
Revises: d4e6f8a0b2c4
Create Date: 2026-11-06 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f7a9b1c3d5'
down_revision = 'd4e6f8a0b2c4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sales') as batch:
        batch.add_column(sa.Column('self_billed', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column('lifecycle_status', sa.String(length=10), nullable=True))
        batch.add_column(sa.Column('lifecycle_reason', sa.Text(), nullable=True))
        batch.add_column(sa.Column('lifecycle_at', sa.DateTime(), nullable=True))
        batch.add_column(sa.Column('received_file', sa.String(length=300), nullable=True))
        batch.drop_constraint('uq_sales_kind_number', type_='unique')
        batch.create_unique_constraint('uq_sales_kind_entity_number', ['kind', 'entity_id', 'number'])


def downgrade():
    with op.batch_alter_table('sales') as batch:
        batch.drop_constraint('uq_sales_kind_entity_number', type_='unique')
        batch.create_unique_constraint('uq_sales_kind_number', ['kind', 'number'])
        batch.drop_column('received_file')
        batch.drop_column('lifecycle_at')
        batch.drop_column('lifecycle_reason')
        batch.drop_column('lifecycle_status')
        batch.drop_column('self_billed')
