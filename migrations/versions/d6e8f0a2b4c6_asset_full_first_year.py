"""immobilisations (lot CG5.d) : amortissement en annuité entière à partir de l'exercice de mise en service

Revision ID: d6e8f0a2b4c6
Revises: c5d7e9f1a3b5
Create Date: 2026-11-08 03:00:00.000000

Les fiches existantes gardent leur plan (colonne nulle = prorata depuis la date de mise en service).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd6e8f0a2b4c6'
down_revision = 'c5d7e9f1a3b5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('assets') as batch:
        batch.add_column(sa.Column('full_first_year', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('assets') as batch:
        batch.drop_column('full_first_year')
