"""module Ventes (lot S2) : encaissements des factures, message de relance

Revision ID: d4e6f8a0b2c5
Revises: c3d5e7f9a1b4
Create Date: 2026-10-23 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e6f8a0b2c5'
down_revision = 'c3d5e7f9a1b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sale_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sale_id', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('paid_on', sa.Date(), nullable=False),
        sa.Column('origin', sa.String(length=8), nullable=False),
        sa.Column('method', sa.String(length=12), nullable=True),
        sa.Column('bank_transaction_id', sa.Integer(), nullable=True),
        sa.Column('bank_account_id', sa.Integer(), nullable=True),
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('vat_released_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('qonto_marked', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['bank_transaction_id'], ['bank_transactions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sale_payments_sale_id', 'sale_payments', ['sale_id'])
    op.create_index('ix_sale_payments_bank_transaction_id', 'sale_payments', ['bank_transaction_id'])
    with op.batch_alter_table('billing_settings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reminder_subject', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('reminder_body', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('billing_settings', schema=None) as batch_op:
        batch_op.drop_column('reminder_body')
        batch_op.drop_column('reminder_subject')
    op.drop_index('ix_sale_payments_bank_transaction_id', table_name='sale_payments')
    op.drop_index('ix_sale_payments_sale_id', table_name='sale_payments')
    op.drop_table('sale_payments')
