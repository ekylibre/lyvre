"""MSA (lot AG7.e) : catégorie de risques ATEXA de l'exploitant

Revision ID: d8e0f2a4b6c8
Revises: c7d9e1f3a5b7
Create Date: 2026-11-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8e0f2a4b6c8'
down_revision = 'c7d9e1f3a5b7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('msa_people') as batch:
        batch.add_column(sa.Column('atexa_category', sa.String(length=1), nullable=True))


def downgrade():
    with op.batch_alter_table('msa_people') as batch:
        batch.drop_column('atexa_category')
