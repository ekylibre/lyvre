"""module Achats (lot S6 du module Ventes) : abonnements et leurs échéances attendues

Revision ID: a8c0e2f4b6d9
Revises: f6a8b0c2d4e7
Create Date: 2026-10-24 03:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8c0e2f4b6d9'
down_revision = 'f6a8b0c2d4e7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False, server_default='other'),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('amount_fixed', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('frequency', sa.String(length=10), nullable=False, server_default='monthly'),
        sa.Column('due_day', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('bank_account_id', sa.Integer(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('renewal_date', sa.Date(), nullable=True),
        sa.Column('notice_days', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['bank_account_id'], ['bank_accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'subscription_periods',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subscription_id', sa.Integer(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('expected_cents', sa.Integer(), nullable=False),
        sa.Column('purchase_id', sa.Integer(), nullable=True),
        sa.Column('bank_transaction_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='expected'),
        sa.ForeignKeyConstraint(['subscription_id'], ['subscriptions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['purchase_id'], ['purchases.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['bank_transaction_id'], ['bank_transactions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('subscription_id', 'due_date', name='uq_subscription_periods_due'),
    )
    op.create_index('ix_subscription_periods_status', 'subscription_periods', ['status'])


def downgrade():
    op.drop_index('ix_subscription_periods_status', table_name='subscription_periods')
    op.drop_table('subscription_periods')
    op.drop_table('subscriptions')
