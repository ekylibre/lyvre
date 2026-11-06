"""connecteur Ekylibre (lot AG11.d) : correspondance des variantes avec les lignes d'inventaire

Revision ID: e1f3a5b7c9d1
Revises: d0e2f4a6b8c0
Create Date: 2026-11-07 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1f3a5b7c9d1'
down_revision = 'd0e2f4a6b8c0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'ekylibre_variant_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('variant_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('variant_id'),
    )


def downgrade():
    op.drop_table('ekylibre_variant_links')
