"""barèmes d'avances aux cultures (lot CG2.b) : saisie par mois ou en cumul

Revision ID: a3b5c7d9e1f3
Revises: f2a4b6c8d0e2
Create Date: 2026-11-07 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3b5c7d9e1f3'
down_revision = 'f2a4b6c8d0e2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('crop_standards') as batch:
        batch.add_column(sa.Column('entry_mode', sa.String(length=10), nullable=False, server_default='monthly'))
        batch.add_column(sa.Column('start_month', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('crop_standards') as batch:
        batch.drop_column('start_month')
        batch.drop_column('entry_mode')
