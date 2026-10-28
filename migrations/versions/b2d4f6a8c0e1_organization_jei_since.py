"""lot T1 : statut de jeune entreprise innovante (date d'entrée) sur la structure

Revision ID: b2d4f6a8c0e1
Revises: a1c3e5f7b9d2
Create Date: 2026-10-27 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2d4f6a8c0e1'
down_revision = 'a1c3e5f7b9d2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('organization') as batch_op:
        batch_op.add_column(sa.Column('jei_since', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('organization') as batch_op:
        batch_op.drop_column('jei_since')
