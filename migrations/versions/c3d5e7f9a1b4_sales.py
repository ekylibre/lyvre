"""module Ventes (lot S1) : réglages de facturation, factures et avoirs, lignes, compteurs, envois ;
champs de vente du catalogue et des clients ; TVA à l'encaissement par exercice

Revision ID: c3d5e7f9a1b4
Revises: a7c1e5d9b302
Create Date: 2026-10-23 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d5e7f9a1b4'
down_revision = 'a7c1e5d9b302'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'billing_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('legal_form', sa.String(length=100), nullable=True),
        sa.Column('share_capital_cents', sa.Integer(), nullable=True),
        sa.Column('rcs', sa.String(length=100), nullable=True),
        sa.Column('vat_number', sa.String(length=20), nullable=True),
        sa.Column('iban', sa.String(length=34), nullable=True),
        sa.Column('bic', sa.String(length=11), nullable=True),
        sa.Column('payment_terms_days', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('late_penalty_text', sa.Text(), nullable=True),
        sa.Column('recovery_fee', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('discount_text', sa.Text(), nullable=True),
        sa.Column('footer', sa.Text(), nullable=True),
        sa.Column('logo_path', sa.String(length=300), nullable=True),
        sa.Column('send_subject', sa.String(length=255), nullable=True),
        sa.Column('send_body', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'sales',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('source', sa.String(length=8), nullable=False, server_default='app'),
        sa.Column('qonto_emit', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('number', sa.String(length=40), nullable=True),
        sa.Column('series_year', sa.Integer(), nullable=True),
        sa.Column('series_seq', sa.Integer(), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('client_snapshot', sa.Text(), nullable=True),
        sa.Column('issue_date', sa.Date(), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('validity_date', sa.Date(), nullable=True),
        sa.Column('service_start', sa.Date(), nullable=True),
        sa.Column('service_end', sa.Date(), nullable=True),
        sa.Column('operation_type', sa.String(length=8), nullable=False, server_default='services'),
        sa.Column('purchase_order', sa.String(length=100), nullable=True),
        sa.Column('untaxed_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tax_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('paid_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('terms', sa.Text(), nullable=True),
        sa.Column('header', sa.Text(), nullable=True),
        sa.Column('footer', sa.Text(), nullable=True),
        sa.Column('vat_mode', sa.String(length=10), nullable=True),
        sa.Column('quote_id', sa.Integer(), nullable=True),
        sa.Column('invoice_id', sa.Integer(), nullable=True),
        sa.Column('credit_reason', sa.Text(), nullable=True),
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('pdf_path', sa.String(length=300), nullable=True),
        sa.Column('qonto_id', sa.String(length=36), nullable=True),
        sa.Column('qonto_status', sa.String(length=20), nullable=True),
        sa.Column('qonto_attachment_id', sa.String(length=36), nullable=True),
        sa.Column('qonto_error', sa.Text(), nullable=True),
        sa.Column('issued_at', sa.DateTime(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('last_reminder_at', sa.DateTime(), nullable=True),
        sa.Column('reminder_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('raw_payload', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['quote_id'], ['sales.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['invoice_id'], ['sales.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('kind', 'number', name='uq_sales_kind_number'),
        sa.UniqueConstraint('qonto_id'),
    )
    op.create_index('ix_sales_kind_status', 'sales', ['kind', 'status'])
    op.create_index('ix_sales_entity_id', 'sales', ['entity_id'])
    op.create_index('ix_sales_due_date', 'sales', ['due_date'])
    op.create_table(
        'sale_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sale_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('label', sa.String(length=300), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('quantity_milli', sa.Integer(), nullable=False, server_default='1000'),
        sa.Column('unit', sa.String(length=20), nullable=True),
        sa.Column('unit_price_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('discount_bp', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('untaxed_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('vat_rate_bp', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('vat_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('nature', sa.String(length=8), nullable=False, server_default='services'),
        sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sale_lines_sale_id', 'sale_lines', ['sale_id'])
    op.create_table(
        'sale_counters',
        sa.Column('series', sa.String(length=4), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('last_number', sa.Integer(), nullable=False, server_default='0'),
        sa.PrimaryKeyConstraint('series', 'year'),
    )
    op.create_table(
        'sale_emails',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sale_id', sa.Integer(), nullable=False),
        sa.Column('purpose', sa.String(length=10), nullable=False),
        sa.Column('channel', sa.String(length=6), nullable=False, server_default='smtp'),
        sa.Column('recipients', sa.Text(), nullable=False),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('status', sa.String(length=8), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_sale_emails_sale_id', 'sale_emails', ['sale_id'])
    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.add_column(sa.Column('customer_account_code', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('billing_emails', sa.Text(), nullable=True))
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('unit', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('sale_price_cents', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('nature', sa.String(length=8), nullable=False, server_default='services'))
    with op.batch_alter_table('fiscal_years', schema=None) as batch_op:
        batch_op.add_column(sa.Column('vat_on_receipts', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    with op.batch_alter_table('fiscal_years', schema=None) as batch_op:
        batch_op.drop_column('vat_on_receipts')
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('nature')
        batch_op.drop_column('sale_price_cents')
        batch_op.drop_column('unit')
        batch_op.drop_column('description')
    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.drop_column('billing_emails')
        batch_op.drop_column('customer_account_code')
    op.drop_index('ix_sale_emails_sale_id', table_name='sale_emails')
    op.drop_table('sale_emails')
    op.drop_table('sale_counters')
    op.drop_index('ix_sale_lines_sale_id', table_name='sale_lines')
    op.drop_table('sale_lines')
    op.drop_index('ix_sales_due_date', table_name='sales')
    op.drop_index('ix_sales_entity_id', table_name='sales')
    op.drop_index('ix_sales_kind_status', table_name='sales')
    op.drop_table('sales')
    op.drop_table('billing_settings')
