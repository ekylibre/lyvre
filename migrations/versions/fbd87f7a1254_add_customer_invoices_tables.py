"""add customer_invoices and customer_invoice_lines tables

Revision ID: fbd87f7a1254
Revises: 0cf63a01caf5
Create Date: 2026-05-15 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fbd87f7a1254'
down_revision = '0cf63a01caf5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'customer_invoices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('odoo_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=True),
        sa.Column('ref', sa.String(length=200), nullable=True),
        sa.Column('state', sa.String(length=20), nullable=True),
        sa.Column('payment_state', sa.String(length=20), nullable=True),
        sa.Column('partner_id', sa.Integer(), nullable=True),
        sa.Column('partner_name', sa.String(length=200), nullable=True),
        sa.Column('partner_email', sa.String(length=200), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('invoice_date', sa.Date(), nullable=True),
        sa.Column('invoice_date_due', sa.Date(), nullable=True),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('amount_untaxed_cents', sa.Integer(), nullable=False),
        sa.Column('amount_tax_cents', sa.Integer(), nullable=False),
        sa.Column('amount_total_cents', sa.Integer(), nullable=False),
        sa.Column('amount_residual_cents', sa.Integer(), nullable=False),
        sa.Column('invoice_origin', sa.String(length=200), nullable=True),
        sa.Column('journal_name', sa.String(length=100), nullable=True),
        sa.Column('narration', sa.Text(), nullable=True),
        sa.Column('raw_payload', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('imported_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('customer_invoices', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_customer_invoices_odoo_id'), ['odoo_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_customer_invoices_name'), ['name'], unique=False)
        batch_op.create_index(batch_op.f('ix_customer_invoices_state'), ['state'], unique=False)
        batch_op.create_index(batch_op.f('ix_customer_invoices_payment_state'), ['payment_state'], unique=False)
        batch_op.create_index(batch_op.f('ix_customer_invoices_partner_email'), ['partner_email'], unique=False)
        batch_op.create_index(batch_op.f('ix_customer_invoices_entity_id'), ['entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_customer_invoices_invoice_date'), ['invoice_date'], unique=False)

    op.create_table(
        'customer_invoice_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('odoo_id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=True),
        sa.Column('product_name', sa.String(length=300), nullable=True),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('qty', sa.Float(), nullable=False),
        sa.Column('price_unit_cents', sa.Integer(), nullable=False),
        sa.Column('discount', sa.Float(), nullable=False),
        sa.Column('price_subtotal_cents', sa.Integer(), nullable=False),
        sa.Column('price_total_cents', sa.Integer(), nullable=False),
        sa.Column('tax_ids', sa.String(length=200), nullable=True),
        sa.Column('account_code', sa.String(length=20), nullable=True),
        sa.Column('raw_payload', sa.Text(), nullable=True),
        sa.Column('imported_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['invoice_id'], ['customer_invoices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('customer_invoice_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_customer_invoice_lines_odoo_id'), ['odoo_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_customer_invoice_lines_invoice_id'), ['invoice_id'], unique=False)


def downgrade():
    with op.batch_alter_table('customer_invoice_lines', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_customer_invoice_lines_invoice_id'))
        batch_op.drop_index(batch_op.f('ix_customer_invoice_lines_odoo_id'))
    op.drop_table('customer_invoice_lines')

    with op.batch_alter_table('customer_invoices', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_customer_invoices_invoice_date'))
        batch_op.drop_index(batch_op.f('ix_customer_invoices_entity_id'))
        batch_op.drop_index(batch_op.f('ix_customer_invoices_partner_email'))
        batch_op.drop_index(batch_op.f('ix_customer_invoices_payment_state'))
        batch_op.drop_index(batch_op.f('ix_customer_invoices_state'))
        batch_op.drop_index(batch_op.f('ix_customer_invoices_name'))
        batch_op.drop_index(batch_op.f('ix_customer_invoices_odoo_id'))
    op.drop_table('customer_invoices')
