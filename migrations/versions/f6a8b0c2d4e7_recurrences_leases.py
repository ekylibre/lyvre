"""module Ventes (lot S5) : factures récurrentes, baux, quittances et reçus de loyer

Revision ID: f6a8b0c2d4e7
Revises: e5f7a9b1c3d6
Create Date: 2026-10-24 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a8b0c2d4e7'
down_revision = 'e5f7a9b1c3d6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'recurrences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('template_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('frequency', sa.String(length=10), nullable=False),
        sa.Column('due_day', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('in_advance', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('next_date', sa.Date(), nullable=False),
        sa.Column('qonto_emit', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['template_id'], ['sales.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'sale_occurrences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('recurrence_id', sa.Integer(), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('sale_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['recurrence_id'], ['recurrences.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('recurrence_id', 'period_start', name='uq_sale_occurrences_period'),
    )
    op.create_table(
        'leases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('unit_label', sa.String(length=200), nullable=False),
        sa.Column('address_line1', sa.String(length=200), nullable=True),
        sa.Column('address_line2', sa.String(length=200), nullable=True),
        sa.Column('postal_code', sa.String(length=10), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('rent_cents', sa.Integer(), nullable=False),
        sa.Column('charges_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('due_day', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('deposit_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('deposit_entry_id', sa.Integer(), nullable=True),
        sa.Column('rent_account_id', sa.Integer(), nullable=True),
        sa.Column('charges_account_id', sa.Integer(), nullable=True),
        sa.Column('recurrence_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['deposit_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['rent_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['charges_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['recurrence_id'], ['recurrences.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'rent_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lease_id', sa.Integer(), nullable=False),
        sa.Column('sale_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=True),
        sa.Column('period_end', sa.Date(), nullable=True),
        sa.Column('rent_cents', sa.Integer(), nullable=False),
        sa.Column('charges_cents', sa.Integer(), nullable=False),
        sa.Column('paid_cents', sa.Integer(), nullable=False),
        sa.Column('paid_on', sa.Date(), nullable=True),
        sa.Column('pdf_path', sa.String(length=300), nullable=True),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['lease_id'], ['leases.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recurrence_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('lease_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_sales_recurrence', 'recurrences', ['recurrence_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_sales_lease', 'leases', ['lease_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('sales', schema=None) as batch_op:
        batch_op.drop_constraint('fk_sales_lease', type_='foreignkey')
        batch_op.drop_constraint('fk_sales_recurrence', type_='foreignkey')
        batch_op.drop_column('lease_id')
        batch_op.drop_column('recurrence_id')
    op.drop_table('rent_receipts')
    op.drop_table('leases')
    op.drop_table('sale_occurrences')
    op.drop_table('recurrences')
