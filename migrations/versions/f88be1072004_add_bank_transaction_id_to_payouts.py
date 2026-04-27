"""add bank_transaction_id to payouts

Revision ID: f88be1072004
Revises: dd0cf5a1c7b4
Create Date: 2026-04-26 20:16:49.712894

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f88be1072004'
down_revision = 'dd0cf5a1c7b4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('payouts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bank_transaction_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_payouts_bank_transaction_id'), ['bank_transaction_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_payouts_bank_transaction_id',
            'bank_transactions',
            ['bank_transaction_id'], ['id'],
            ondelete='SET NULL',
        )


def downgrade():
    with op.batch_alter_table('payouts', schema=None) as batch_op:
        batch_op.drop_constraint('fk_payouts_bank_transaction_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_payouts_bank_transaction_id'))
        batch_op.drop_column('bank_transaction_id')
