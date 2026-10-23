"""module Associés (lot A1) : associés, registre des parts, notes de frais, taux d'intérêt par défaut

Revision ID: a7c1e5d9b302
Revises: f6b1d4e8a207
Create Date: 2026-10-23 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7c1e5d9b302'
down_revision = 'f6b1d4e8a207'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'associates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('interest_rate_bp', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entity_id'),
        sa.UniqueConstraint('account_id'),
    )
    op.create_table(
        'share_movements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('movement_date', sa.Date(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('nominal_cents', sa.Integer(), nullable=True),
        sa.Column('price_cents', sa.Integer(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('attachment_path', sa.String(length=300), nullable=True),
        sa.Column('attachment_name', sa.String(length=200), nullable=True),
        sa.Column('attachment_mime', sa.String(length=50), nullable=True),
        sa.Column('attachment_size', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_share_movements_movement_date', 'share_movements', ['movement_date'])
    op.create_table(
        'share_movement_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('movement_id', sa.Integer(), nullable=False),
        sa.Column('associate_id', sa.Integer(), nullable=False),
        sa.Column('nature', sa.String(length=10), nullable=False),
        sa.Column('parts', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['movement_id'], ['share_movements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['associate_id'], ['associates.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_share_movement_lines_movement_id', 'share_movement_lines', ['movement_id'])
    op.create_index('ix_share_movement_lines_associate_id', 'share_movement_lines', ['associate_id'])
    op.create_table(
        'associate_expenses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('associate_id', sa.Integer(), nullable=False),
        sa.Column('expense_date', sa.Date(), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('untaxed_cents', sa.Integer(), nullable=False),
        sa.Column('vat_rate_bp', sa.Integer(), nullable=True),
        sa.Column('vat_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_cents', sa.Integer(), nullable=False),
        sa.Column('attachment_path', sa.String(length=300), nullable=True),
        sa.Column('attachment_name', sa.String(length=200), nullable=True),
        sa.Column('attachment_mime', sa.String(length=50), nullable=True),
        sa.Column('attachment_size', sa.Integer(), nullable=True),
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['associate_id'], ['associates.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id']),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_associate_expenses_associate_id', 'associate_expenses', ['associate_id'])
    with op.batch_alter_table('organization', schema=None) as batch_op:
        batch_op.add_column(sa.Column('associate_interest_rate_bp', sa.Integer(), nullable=False, server_default='0'))
    with op.batch_alter_table('purchase_payments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('associate_id', sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f('ix_purchase_payments_associate_id'), ['associate_id'], unique=False)
        batch_op.create_foreign_key('fk_purchase_payments_associate_id', 'associates',
                                    ['associate_id'], ['id'], ondelete='RESTRICT')
    # Au plus un règlement par un associé par facture.
    op.create_index('uq_purchase_payments_associate', 'purchase_payments', ['purchase_id'], unique=True,
                    sqlite_where=sa.text("origin = 'associate'"),
                    postgresql_where=sa.text("origin = 'associate'"))


def downgrade():
    op.drop_index('uq_purchase_payments_associate', table_name='purchase_payments')
    with op.batch_alter_table('purchase_payments', schema=None) as batch_op:
        batch_op.drop_constraint('fk_purchase_payments_associate_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_purchase_payments_associate_id'))
        batch_op.drop_column('associate_id')
    with op.batch_alter_table('organization', schema=None) as batch_op:
        batch_op.drop_column('associate_interest_rate_bp')
    op.drop_index('ix_associate_expenses_associate_id', table_name='associate_expenses')
    op.drop_table('associate_expenses')
    op.drop_index('ix_share_movement_lines_associate_id', table_name='share_movement_lines')
    op.drop_index('ix_share_movement_lines_movement_id', table_name='share_movement_lines')
    op.drop_table('share_movement_lines')
    op.drop_index('ix_share_movements_movement_date', table_name='share_movements')
    op.drop_table('share_movements')
    op.drop_table('associates')
