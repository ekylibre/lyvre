"""profil des démarches d'une exploitation (lot AG9a, échéancier) : organization.agri_profile

Revision ID: a7b9d1f3e5c6
Revises: f6a8c0e2d4b5
Create Date: 2026-11-04 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b9d1f3e5c6'
down_revision = 'f6a8c0e2d4b5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('organization') as batch_op:
        batch_op.add_column(sa.Column('agri_profile', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('organization') as batch_op:
        batch_op.drop_column('agri_profile')
