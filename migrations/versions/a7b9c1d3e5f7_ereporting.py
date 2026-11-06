"""e-reporting B2C (lot AG10.e) : catégories de vente directe, exports

Revision ID: a7b9c1d3e5f7
Revises: f6a8b0c2d4e6
Create Date: 2026-11-07 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b9c1d3e5f7'
down_revision = 'f6a8b0c2d4e6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('simple_categories') as batch:
        batch.add_column(sa.Column('direct_sale', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        'ereporting_exports',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('transactions', sa.Integer(), nullable=False),
        sa.Column('base_cents', sa.Integer(), nullable=False),
        sa.Column('tax_cents', sa.Integer(), nullable=False),
        sa.Column('exported_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('ereporting_exports')
    with op.batch_alter_table('simple_categories') as batch:
        batch.drop_column('direct_sale')
