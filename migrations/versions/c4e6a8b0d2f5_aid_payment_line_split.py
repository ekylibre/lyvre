"""aides : une ligne d'écriture 74 ventilée entre plusieurs dossiers (essai de l'interface, 09/11/2026)

Revision ID: c4e6a8b0d2f5
Revises: b3d5f7a9c1e4
Create Date: 2026-11-09 22:15:00.000000

"""
from alembic import op


revision = 'c4e6a8b0d2f5'
down_revision = 'b3d5f7a9c1e4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('aid_payments') as batch:
        batch.drop_index('ix_aid_payments_journal_line_id')
        batch.create_index('ix_aid_payments_journal_line_id', ['journal_line_id'], unique=False)


def downgrade():
    with op.batch_alter_table('aid_payments') as batch:
        batch.drop_index('ix_aid_payments_journal_line_id')
        batch.create_index('ix_aid_payments_journal_line_id', ['journal_line_id'], unique=True)
