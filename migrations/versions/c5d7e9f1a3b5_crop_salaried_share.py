"""avances aux cultures (lot CG5.a) : part de main-d'œuvre salariée appliquée au barème (F, M1)

Revision ID: c5d7e9f1a3b5
Revises: b4c6d8e0f2a4
Create Date: 2026-11-08 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5d7e9f1a3b5'
down_revision = 'b4c6d8e0f2a4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('crop_advances') as batch:
        batch.add_column(sa.Column('salaried_share_bp', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('crop_advances') as batch:
        batch.drop_column('salaried_share_bp')
