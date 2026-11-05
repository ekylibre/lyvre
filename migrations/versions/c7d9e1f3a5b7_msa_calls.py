"""MSA (lot AG7.c) : registre des appels de cotisations

Revision ID: c7d9e1f3a5b7
Revises: b6c8d0e2f4a6
Create Date: 2026-11-05 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7d9e1f3a5b7'
down_revision = 'b6c8d0e2f4a6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'msa_calls',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=14), nullable=False),
        sa.Column('due_on', sa.Date(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('base_cents', sa.Integer(), nullable=True),
        sa.Column('contributions_cents', sa.Integer(), nullable=True),
        sa.Column('csg_deductible_cents', sa.Integer(), nullable=True),
        sa.Column('csg_crds_non_deductible_cents', sa.Integer(), nullable=True),
        sa.Column('third_party_cents', sa.Integer(), nullable=True),
        sa.Column('estimated', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('bank_transaction_id', sa.Integer(), nullable=True),
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['person_id'], ['msa_people.id'], name='fk_msa_calls_person_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['bank_transaction_id'], ['bank_transactions.id'], name='fk_msa_calls_bank_transaction_id', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], name='fk_msa_calls_journal_entry_id', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('msa_calls') as batch:
        batch.create_index('ix_msa_calls_person_id', ['person_id'])
        batch.create_index('ix_msa_calls_year', ['year'])


def downgrade():
    with op.batch_alter_table('msa_calls') as batch:
        batch.drop_index('ix_msa_calls_year')
        batch.drop_index('ix_msa_calls_person_id')
    op.drop_table('msa_calls')
