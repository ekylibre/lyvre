"""lot F5 : immobilisations et amortissements

Revision ID: f5b7c9d1e3a5
Revises: e4a6b8c0d2f4
Create Date: 2026-10-24 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f5b7c9d1e3a5'
down_revision = 'e4a6b8c0d2f4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('depreciation_account_id', sa.Integer(), nullable=True),
        sa.Column('expense_account_id', sa.Integer(), nullable=True),
        sa.Column('waiting_account_id', sa.Integer(), nullable=True),
        sa.Column('acquired_on', sa.Date(), nullable=False),
        sa.Column('in_service_date', sa.Date(), nullable=True),
        sa.Column('acquisition_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('residual_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('method', sa.String(length=10), nullable=False, server_default='linear'),
        sa.Column('duration_months', sa.Integer(), nullable=True),
        sa.Column('fiscal_coefficient', sa.Numeric(4, 2), nullable=True),
        sa.Column('prior_depreciation_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('prior_as_of', sa.Date(), nullable=True),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('purchase_line_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='in_use'),
        sa.Column('in_service_entry_id', sa.Integer(), nullable=True),
        sa.Column('disposal_date', sa.Date(), nullable=True),
        sa.Column('disposal_price_cents', sa.Integer(), nullable=True),
        sa.Column('disposal_entry_id', sa.Integer(), nullable=True),
        sa.Column('sale_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['assets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['depreciation_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['expense_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['waiting_account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['purchase_line_id'], ['purchase_lines.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['in_service_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['disposal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sale_id'], ['sales.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_assets_parent_id', 'assets', ['parent_id'])
    op.create_table(
        'asset_depreciations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('started_on', sa.Date(), nullable=False),
        sa.Column('stopped_on', sa.Date(), nullable=False),
        sa.Column('days', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('entry_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', 'fiscal_year_id', name='uq_asset_depreciation_year'),
    )
    with op.batch_alter_table('organization', schema=None) as batch_op:
        batch_op.add_column(sa.Column('depreciation_enabled', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('organization', schema=None) as batch_op:
        batch_op.drop_column('depreciation_enabled')
    op.drop_table('asset_depreciations')
    op.drop_index('ix_assets_parent_id', table_name='assets')
    op.drop_table('assets')
