"""qonto bank sync: bank account link, transaction source and details, ignored counterparties

Revision ID: d7a2e6f0b318
Revises: c3f8a1d5e297
Create Date: 2026-10-20 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7a2e6f0b318'
down_revision = 'c3f8a1d5e297'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bank_accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('qonto_account_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('qonto_sync_from', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('qonto_synced_at', sa.DateTime(), nullable=True))
        batch_op.create_unique_constraint('uq_bank_accounts_qonto_account_id', ['qonto_account_id'])

    with op.batch_alter_table('bank_transactions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source', sa.String(length=10), nullable=False, server_default='ofx'))
        batch_op.alter_column('raw_type', existing_type=sa.String(length=20), type_=sa.String(length=40))
        batch_op.add_column(sa.Column('counterparty', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('note', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('is_reversed', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('attachment_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('attachment_required', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('attachment_lost', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('source_updated_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_bank_transactions_account_reversed', ['bank_account_id', 'is_reversed'], unique=False)

    with op.batch_alter_table('sync_jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('bank_account_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_sync_jobs_bank_account_id'), ['bank_account_id'], unique=False)
        batch_op.create_foreign_key('fk_sync_jobs_bank_account_id', 'bank_accounts',
                                    ['bank_account_id'], ['id'], ondelete='SET NULL')

    op.create_table(
        'ignored_counterparties',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name_key', sa.String(length=200), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name_key'),
    )


def downgrade():
    op.drop_table('ignored_counterparties')

    with op.batch_alter_table('sync_jobs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sync_jobs_bank_account_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_sync_jobs_bank_account_id'))
        batch_op.drop_column('bank_account_id')

    with op.batch_alter_table('bank_transactions', schema=None) as batch_op:
        batch_op.drop_index('ix_bank_transactions_account_reversed')
        batch_op.drop_column('source_updated_at')
        batch_op.drop_column('attachment_lost')
        batch_op.drop_column('attachment_required')
        batch_op.drop_column('attachment_count')
        batch_op.drop_column('is_reversed')
        batch_op.drop_column('note')
        batch_op.drop_column('counterparty')
        batch_op.alter_column('raw_type', existing_type=sa.String(length=40), type_=sa.String(length=20))
        batch_op.drop_column('source')

    with op.batch_alter_table('bank_accounts', schema=None) as batch_op:
        batch_op.drop_constraint('uq_bank_accounts_qonto_account_id', type_='unique')
        batch_op.drop_column('qonto_synced_at')
        batch_op.drop_column('qonto_sync_from')
        batch_op.drop_column('qonto_account_id')
