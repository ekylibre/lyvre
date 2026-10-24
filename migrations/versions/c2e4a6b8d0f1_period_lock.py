"""lot F2 : date de verrouillage des exercices

Revision ID: c2e4a6b8d0f1
Revises: b1d3f5a7c9e2
Create Date: 2026-10-24 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2e4a6b8d0f1'
down_revision = 'b1d3f5a7c9e2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('fiscal_years', schema=None) as batch_op:
        batch_op.add_column(sa.Column('locked_until', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('lock_before_close', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('fiscal_years', schema=None) as batch_op:
        batch_op.drop_column('lock_before_close')
        batch_op.drop_column('locked_until')
