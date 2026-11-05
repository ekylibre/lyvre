"""biens vivants immobilisés (lot AG5.a) : nature, espèce, catégorie d'âge, effectif, origine des immobilisations

Revision ID: f8a0b2c4d6e7
Revises: e7f9a1b3c5d6
Create Date: 2026-11-05 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f8a0b2c4d6e7'
down_revision = 'e7f9a1b3c5d6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('assets') as batch_op:
        batch_op.add_column(sa.Column('living_kind', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('species', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('age_class', sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column('units', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('origin', sa.String(length=12), nullable=True))


def downgrade():
    with op.batch_alter_table('assets') as batch_op:
        batch_op.drop_column('origin')
        batch_op.drop_column('units')
        batch_op.drop_column('age_class')
        batch_op.drop_column('species')
        batch_op.drop_column('living_kind')
