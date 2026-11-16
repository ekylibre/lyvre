"""connecteur Ekylibre (lot AG11.a) : instantanés des données lues

Revision ID: b8c0d2e4f6a8
Revises: a7b9c1d3e5f7
Create Date: 2026-11-07 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8c0d2e4f6a8'
down_revision = 'a7b9c1d3e5f7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ekylibre_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('kind'),
    )


def downgrade():
    op.drop_table('ekylibre_snapshots')
