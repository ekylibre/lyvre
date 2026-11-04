"""acomptes de TVA du régime simplifié agricole (lot AG2.c, 3525 bis) : référence saisie de l'année précédente

Revision ID: e5f7b9d1c3a4
Revises: d4e6a8c0b2f3
Create Date: 2026-11-04 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f7b9d1c3a4'
down_revision = 'd4e6a8c0b2f3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('fiscal_years') as batch_op:
        batch_op.add_column(sa.Column('vat_reference_cents', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('vat_reference_assets_cents', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('fiscal_years') as batch_op:
        batch_op.drop_column('vat_reference_assets_cents')
        batch_op.drop_column('vat_reference_cents')
