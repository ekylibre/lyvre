"""comptabilité simplifiée (lot D.2) : catégories de recettes et de dépenses

Revision ID: f6b1d4e8a207
Revises: e5a9c3d7f106
Create Date: 2026-10-25 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6b1d4e8a207'
down_revision = 'e5a9c3d7f106'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'simple_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('label', sa.String(length=120), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )


def downgrade():
    op.drop_table('simple_categories')
