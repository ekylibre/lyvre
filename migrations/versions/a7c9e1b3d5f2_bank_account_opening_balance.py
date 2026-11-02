"""solde bancaire d'ouverture des comptes bancaires (colonne « Solde bancaire »)

Revision ID: a7c9e1b3d5f2
Revises: f6b8d0e2a4c5
Create Date: 2026-11-02 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c9e1b3d5f2'
down_revision = 'f6b8d0e2a4c5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bank_accounts') as batch_op:
        batch_op.add_column(sa.Column('opening_balance_cents', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('opening_balance_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('opening_entry_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_bank_accounts_opening_entry', 'journal_entries', ['opening_entry_id'], ['id'],
                                    ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('bank_accounts') as batch_op:
        batch_op.drop_constraint('fk_bank_accounts_opening_entry', type_='foreignkey')
        batch_op.drop_column('opening_entry_id')
        batch_op.drop_column('opening_balance_date')
        batch_op.drop_column('opening_balance_cents')
