"""intégration SUPER PDP : envoi des ventes et réception des achats (lot PDP1)

Revision ID: f1a3c5e7b9d2
Revises: e7f9a1b3c5d7
Create Date: 2026-11-08 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f1a3c5e7b9d2'
down_revision = 'e7f9a1b3c5d7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sales') as batch:
        batch.add_column(sa.Column('pdp_id', sa.String(length=32), nullable=True))
        batch.add_column(sa.Column('pdp_status', sa.String(length=40), nullable=True))
        batch.add_column(sa.Column('pdp_error', sa.Text(), nullable=True))
        batch.add_column(sa.Column('pdp_sent_at', sa.DateTime(), nullable=True))
        batch.create_index('ix_sales_pdp_id', ['pdp_id'], unique=True)
    with op.batch_alter_table('purchases') as batch:
        batch.add_column(sa.Column('pdp_id', sa.String(length=32), nullable=True))
        batch.add_column(sa.Column('pdp_status', sa.String(length=40), nullable=True))
        batch.create_index('ix_purchases_pdp_id', ['pdp_id'], unique=True)


def downgrade():
    with op.batch_alter_table('purchases') as batch:
        batch.drop_index('ix_purchases_pdp_id')
        batch.drop_column('pdp_status')
        batch.drop_column('pdp_id')
    with op.batch_alter_table('sales') as batch:
        batch.drop_index('ix_sales_pdp_id')
        batch.drop_column('pdp_sent_at')
        batch.drop_column('pdp_error')
        batch.drop_column('pdp_status')
        batch.drop_column('pdp_id')
