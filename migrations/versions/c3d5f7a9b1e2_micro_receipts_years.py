"""recettes du micro-BA des années antérieures (lot AG1.d, comptabilité agricole)

Revision ID: c3d5f7a9b1e2
Revises: b2c4e6a8f0d1
Create Date: 2026-11-04 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d5f7a9b1e2'
down_revision = 'b2c4e6a8f0d1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'micro_receipts_years',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('receipts_cents', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year'),
    )


def downgrade():
    op.drop_table('micro_receipts_years')
