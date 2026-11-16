"""analytique agricole (lot AG8.c) : affectation sur les sources (achats, règles, aides) et activité des inventaires
et immobilisations

Revision ID: a1b3c5d7e9f1
Revises: f0a2b4c6d8e0
Create Date: 2026-11-06 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b3c5d7e9f1'
down_revision = 'f0a2b4c6d8e0'
branch_labels = None
depends_on = None

TARGET_TABLES = ('purchase_lines', 'rules', 'aids')
ACTIVITY_TABLES = ('stock_lines', 'stock_lots', 'crop_advances', 'assets')


def upgrade():
    for table in TARGET_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column('analytic_target', sa.String(length=24), nullable=True))
    for table in ACTIVITY_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column('activity_id', sa.Integer(), nullable=True))
            batch.create_foreign_key(f'fk_{table}_activity_id', 'activities', ['activity_id'], ['id'], ondelete='SET NULL')


def downgrade():
    for table in ACTIVITY_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f'fk_{table}_activity_id', type_='foreignkey')
            batch.drop_column('activity_id')
    for table in TARGET_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column('analytic_target')
