"""aides : versement rattaché à une ligne d'écriture (aides comptabilisées sans dossier, essai de l'interface 09/11/2026)

Revision ID: b3d5f7a9c1e4
Revises: a2c4e6f8b1d3
Create Date: 2026-11-09 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3d5f7a9c1e4'
down_revision = 'a2c4e6f8b1d3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('aid_payments') as batch:
        batch.add_column(sa.Column('journal_line_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_aid_payments_journal_line_id', 'journal_lines', ['journal_line_id'], ['id'],
                                 ondelete='SET NULL')
        batch.create_index('ix_aid_payments_journal_line_id', ['journal_line_id'], unique=True)


def downgrade():
    with op.batch_alter_table('aid_payments') as batch:
        batch.drop_index('ix_aid_payments_journal_line_id')
        batch.drop_constraint('fk_aid_payments_journal_line_id', type_='foreignkey')
        batch.drop_column('journal_line_id')
