"""décomptes de coopérative : journal choisi (essai de l'interface, 10/11/2026)

Un dossier tenu avec un journal par coopérative (KA, KB…) passe ses décomptes dans ce journal ; vide : journal des
ventes (VE), comme avant.

Revision ID: e6a8c0d2f4b7
Revises: d5f7b9c1e3a6
Create Date: 2026-11-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e6a8c0d2f4b7'
down_revision = 'd5f7b9c1e3a6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('coop_statements') as batch:
        batch.add_column(sa.Column('journal_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_coop_statements_journal_id', 'journals', ['journal_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('coop_statements') as batch:
        batch.drop_constraint('fk_coop_statements_journal_id', type_='foreignkey')
        batch.drop_column('journal_id')
