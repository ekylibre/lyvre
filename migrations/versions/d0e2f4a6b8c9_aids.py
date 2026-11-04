"""aides PAC et subventions (lot AG3.a) : dossiers d'aide et versements

Revision ID: d0e2f4a6b8c9
Revises: c9d1f3b5e7a8
Create Date: 2026-11-04 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd0e2f4a6b8c9'
down_revision = 'c9d1f3b5e7a8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'aids',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scheme', sa.String(length=40), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('campaign', sa.Integer(), nullable=False),
        sa.Column('funder_entity_id', sa.Integer(), nullable=True),
        sa.Column('payer', sa.String(length=60), nullable=True),
        sa.Column('nature', sa.String(length=12), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('operating_account_id', sa.Integer(), nullable=True),
        sa.Column('investment_share_cents', sa.Integer(), nullable=True),
        sa.Column('trigger', sa.String(length=14), nullable=False),
        sa.Column('decision_on', sa.Date(), nullable=True),
        sa.Column('requested_cents', sa.Integer(), nullable=True),
        sa.Column('notified_cents', sa.Integer(), nullable=True),
        sa.Column('notified_on', sa.Date(), nullable=True),
        sa.Column('payment_request_deadline', sa.Date(), nullable=True),
        sa.Column('payment_requested_on', sa.Date(), nullable=True),
        sa.Column('commitment_end_on', sa.Date(), nullable=True),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='requested'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['funder_entity_id'], ['entities.id'], name='fk_aids_funder_entity_id', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name='fk_aids_account_id', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['operating_account_id'], ['accounts.id'], name='fk_aids_operating_account_id',
                                ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_aids_campaign', 'aids', ['campaign'])
    op.create_table(
        'aid_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('aid_id', sa.Integer(), nullable=False),
        sa.Column('paid_on', sa.Date(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('bank_transaction_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['aid_id'], ['aids.id'], name='fk_aid_payments_aid_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['bank_transaction_id'], ['bank_transactions.id'],
                                name='fk_aid_payments_bank_transaction_id', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_aid_payments_aid_id', 'aid_payments', ['aid_id'])
    op.create_index('ix_aid_payments_bank_transaction_id', 'aid_payments', ['bank_transaction_id'])


def downgrade():
    op.drop_index('ix_aid_payments_bank_transaction_id', table_name='aid_payments')
    op.drop_index('ix_aid_payments_aid_id', table_name='aid_payments')
    op.drop_table('aid_payments')
    op.drop_index('ix_aids_campaign', table_name='aids')
    op.drop_table('aids')
