"""connecteur Ekylibre (lot AG11.b) : activité Ekylibre rattachée

Revision ID: c9d1e3f5a7b9
Revises: b8c0d2e4f6a8
Create Date: 2026-11-07 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d1e3f5a7b9'
down_revision = 'b8c0d2e4f6a8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('activities') as batch:
        batch.add_column(sa.Column('ekylibre_id', sa.Integer(), nullable=True))
        batch.create_index('ix_activities_ekylibre_id', ['ekylibre_id'])


def downgrade():
    with op.batch_alter_table('activities') as batch:
        batch.drop_index('ix_activities_ekylibre_id')
        batch.drop_column('ekylibre_id')
