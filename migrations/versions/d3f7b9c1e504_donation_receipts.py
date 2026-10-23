"""reçus fiscaux (lot B.2) : compteurs, reçus, dons repris, dons en nature, donateur d'une ligne

Revision ID: d3f7b9c1e504
Revises: c1e5a7b9d402
Create Date: 2026-10-23 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3f7b9c1e504'
down_revision = 'c1e5a7b9d402'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'receipt_counters',
        sa.Column('year', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('last_number', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('year'),
    )
    op.create_table(
        'in_kind_donations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('description', sa.String(length=300), nullable=False),
        sa.Column('valuation_cents', sa.Integer(), nullable=False),
        sa.Column('valuation_method', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_in_kind_donations_entity_id', 'in_kind_donations', ['entity_id'])
    op.create_table(
        'donation_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('number', sa.String(length=12), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('person_kind', sa.String(length=12), nullable=False),
        sa.Column('mode', sa.String(length=10), nullable=False),
        sa.Column('total_cents', sa.Integer(), nullable=False),
        sa.Column('donor_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('cancel_reason', sa.Text(), nullable=True),
        sa.Column('replaced_by_id', sa.Integer(), nullable=True),
        sa.Column('pdf_path', sa.String(length=300), nullable=True),
        sa.Column('pdf_sha256', sa.String(length=64), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=False),
        sa.Column('issued_by_user_id', sa.Integer(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('sent_to', sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id']),
        sa.ForeignKeyConstraint(['replaced_by_id'], ['donation_receipts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('number'),
    )
    op.create_index('ix_donation_receipts_year', 'donation_receipts', ['year'])
    op.create_index('ix_donation_receipts_entity_id', 'donation_receipts', ['entity_id'])
    op.create_table(
        'donation_receipt_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('receipt_id', sa.Integer(), nullable=False),
        sa.Column('journal_line_id', sa.Integer(), nullable=True),
        sa.Column('in_kind_id', sa.Integer(), nullable=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('nature', sa.String(length=12), nullable=False),
        sa.Column('form', sa.String(length=14), nullable=False),
        sa.Column('payment_method', sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(['receipt_id'], ['donation_receipts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['journal_line_id'], ['journal_lines.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['in_kind_id'], ['in_kind_donations.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    for column in ('receipt_id', 'journal_line_id', 'in_kind_id'):
        op.create_index(f'ix_donation_receipt_items_{column}', 'donation_receipt_items', [column])
    with op.batch_alter_table('journal_lines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('entity_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_journal_lines_entity', 'entities', ['entity_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('journal_lines', schema=None) as batch_op:
        batch_op.drop_constraint('fk_journal_lines_entity', type_='foreignkey')
        batch_op.drop_column('entity_id')
    op.drop_table('donation_receipt_items')
    op.drop_table('donation_receipts')
    op.drop_table('in_kind_donations')
    op.drop_table('receipt_counters')
