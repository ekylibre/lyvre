"""qonto purchases: catalogue, supplier invoices, lines, payments, sync cursors

Revision ID: 24e66976825c
Revises: d7a2e6f0b318
Create Date: 2026-10-21 22:21:21.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '24e66976825c'
down_revision = 'd7a2e6f0b318'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('sync_cursors',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('key', sa.String(length=50), nullable=False),
    sa.Column('sync_from', sa.Date(), nullable=True),
    sa.Column('synced_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_table('products',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('reference', sa.String(length=50), nullable=True),
    sa.Column('kind', sa.String(length=10), nullable=False),
    sa.Column('purchase_account_id', sa.Integer(), nullable=True),
    sa.Column('sale_account_id', sa.Integer(), nullable=True),
    sa.Column('vat_rate_bp', sa.Integer(), nullable=True),
    sa.Column('active', sa.Boolean(), server_default=sa.true(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['purchase_account_id'], ['accounts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['sale_account_id'], ['accounts.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('purchases',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('source', sa.String(length=10), server_default='qonto', nullable=False),
    sa.Column('qonto_id', sa.String(length=36), nullable=True),
    sa.Column('entity_id', sa.Integer(), nullable=True),
    sa.Column('supplier_name', sa.String(length=200), nullable=True),
    sa.Column('qonto_supplier_id', sa.String(length=36), nullable=True),
    sa.Column('supplier_vat', sa.String(length=30), nullable=True),
    sa.Column('supplier_iban', sa.String(length=34), nullable=True),
    sa.Column('invoice_number', sa.String(length=100), nullable=True),
    sa.Column('issue_date', sa.Date(), nullable=True),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('payment_date', sa.Date(), nullable=True),
    sa.Column('currency', sa.String(length=3), server_default='EUR', nullable=False),
    sa.Column('total_cents', sa.Integer(), nullable=False),
    sa.Column('untaxed_cents', sa.Integer(), nullable=True),
    sa.Column('tax_cents', sa.Integer(), nullable=True),
    sa.Column('payable_cents', sa.Integer(), nullable=True),
    sa.Column('is_credit_note', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('is_einvoice', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('qonto_status', sa.String(length=20), nullable=True),
    sa.Column('is_hidden', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('attachment_id', sa.String(length=36), nullable=True),
    sa.Column('related_qonto_ids', sa.Text(), nullable=True),
    sa.Column('lines_edited', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('journal_entry_id', sa.Integer(), nullable=True),
    sa.Column('review_reason', sa.Text(), nullable=True),
    sa.Column('source_updated_at', sa.DateTime(), nullable=True),
    sa.Column('raw_payload', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('qonto_id')
    )
    with op.batch_alter_table('purchases', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_purchases_entity_id'), ['entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchases_is_hidden'), ['is_hidden'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchases_issue_date'), ['issue_date'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchases_qonto_status'), ['qonto_status'], unique=False)

    op.create_table('purchase_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('purchase_id', sa.Integer(), nullable=False),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('product_id', sa.Integer(), nullable=True),
    sa.Column('account_id', sa.Integer(), nullable=True),
    sa.Column('label', sa.String(length=300), nullable=True),
    sa.Column('untaxed_cents', sa.Integer(), nullable=False),
    sa.Column('vat_rate_bp', sa.Integer(), nullable=True),
    sa.Column('vat_cents', sa.Integer(), nullable=False),
    sa.Column('total_cents', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['purchase_id'], ['purchases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('purchase_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_purchase_lines_purchase_id'), ['purchase_id'], unique=False)

    op.create_table('purchase_payments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('purchase_id', sa.Integer(), nullable=False),
    sa.Column('qonto_transaction_id', sa.String(length=36), nullable=False),
    sa.Column('bank_transaction_id', sa.Integer(), nullable=True),
    sa.Column('journal_entry_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['bank_transaction_id'], ['bank_transactions.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['purchase_id'], ['purchases.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('purchase_id', 'qonto_transaction_id', name='uq_purchase_payment_transaction')
    )
    with op.batch_alter_table('purchase_payments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_purchase_payments_bank_transaction_id'), ['bank_transaction_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_purchase_payments_purchase_id'), ['purchase_id'], unique=False)

    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.add_column(sa.Column('default_product_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('qonto_supplier_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('vat_number', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('iban', sa.String(length=34), nullable=True))
        batch_op.create_index(batch_op.f('ix_entities_qonto_supplier_id'), ['qonto_supplier_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_entities_vat_number'), ['vat_number'], unique=False)
        batch_op.create_foreign_key('fk_entities_default_product_id', 'products',
                                    ['default_product_id'], ['id'], ondelete='SET NULL')

    with op.batch_alter_table('fiscal_years', schema=None) as batch_op:
        batch_op.add_column(sa.Column('vat_liable', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    with op.batch_alter_table('fiscal_years', schema=None) as batch_op:
        batch_op.drop_column('vat_liable')

    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.drop_constraint('fk_entities_default_product_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_entities_vat_number'))
        batch_op.drop_index(batch_op.f('ix_entities_qonto_supplier_id'))
        batch_op.drop_column('iban')
        batch_op.drop_column('vat_number')
        batch_op.drop_column('qonto_supplier_id')
        batch_op.drop_column('default_product_id')

    with op.batch_alter_table('purchase_payments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_purchase_payments_purchase_id'))
        batch_op.drop_index(batch_op.f('ix_purchase_payments_bank_transaction_id'))

    op.drop_table('purchase_payments')
    with op.batch_alter_table('purchase_lines', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_purchase_lines_purchase_id'))

    op.drop_table('purchase_lines')
    with op.batch_alter_table('purchases', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_purchases_qonto_status'))
        batch_op.drop_index(batch_op.f('ix_purchases_issue_date'))
        batch_op.drop_index(batch_op.f('ix_purchases_is_hidden'))
        batch_op.drop_index(batch_op.f('ix_purchases_entity_id'))

    op.drop_table('purchases')
    op.drop_table('products')
    op.drop_table('sync_cursors')
