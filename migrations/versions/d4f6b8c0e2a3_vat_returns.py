"""lot T3 : déclarations de TVA (CA3 mensuelle)

Revision ID: d4f6b8c0e2a3
Revises: c3e5a7b9d1f2
Create Date: 2026-10-28 08:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4f6b8c0e2a3'
down_revision = 'c3e5a7b9d1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'vat_returns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('form', sa.String(length=10), nullable=False, server_default='CA3'),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='validated'),
        sa.Column('boxes_json', sa.Text(), nullable=False),
        sa.Column('credit_carried_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('due_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('credit_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('liquidation_entry_id', sa.Integer(), nullable=True),
        sa.Column('deadline', sa.Date(), nullable=True),
        sa.Column('declared_on', sa.Date(), nullable=True),
        sa.Column('declared_reference', sa.String(length=50), nullable=True),
        sa.Column('validated_at', sa.DateTime(), nullable=True),
        sa.Column('validated_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id']),
        sa.ForeignKeyConstraint(['liquidation_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('period_start', 'form', name='uq_vat_returns_period'),
    )
    with op.batch_alter_table('journal_lines') as batch_op:
        batch_op.add_column(sa.Column('vat_return_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_journal_lines_vat_return', 'vat_returns', ['vat_return_id'], ['id'],
                                    ondelete='SET NULL')
        batch_op.create_index('ix_journal_lines_vat_return_id', ['vat_return_id'])
    with op.batch_alter_table('fiscal_years') as batch_op:
        batch_op.add_column(sa.Column('vat_period', sa.String(length=10), nullable=True))
    with op.batch_alter_table('organization') as batch_op:
        batch_op.add_column(sa.Column('vat_due_day', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('organization') as batch_op:
        batch_op.drop_column('vat_due_day')
    with op.batch_alter_table('fiscal_years') as batch_op:
        batch_op.drop_column('vat_period')
    with op.batch_alter_table('journal_lines') as batch_op:
        batch_op.drop_index('ix_journal_lines_vat_return_id')
        batch_op.drop_constraint('fk_journal_lines_vat_return', type_='foreignkey')
        batch_op.drop_column('vat_return_id')
    op.drop_table('vat_returns')
