"""inventaire de clôture agricole (lot AG4.a) : réglages, barèmes, lignes de stock, feuilles de comptage

Revision ID: b4c6d8e0f2a3
Revises: a3b5c7d9e1f2
Create Date: 2026-11-05 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b4c6d8e0f2a3'
down_revision = 'a3b5c7d9e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'stock_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('discounts_json', sa.Text(), nullable=False),
        sa.Column('counted_on', sa.Date(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_stock_settings_fiscal_year_id',
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fiscal_year_id', name='uq_stock_settings_fiscal_year_id'),
    )
    op.create_table(
        'stock_standards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('unit', sa.String(length=10), nullable=False),
        sa.Column('value_cents', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key', 'year', name='uq_stock_standards_key_year'),
    )
    op.create_table(
        'stock_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('variation_account_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('production', sa.String(length=120), nullable=True),
        sa.Column('quantity', sa.Numeric(14, 3), nullable=False),
        sa.Column('unit', sa.String(length=10), nullable=False),
        sa.Column('method', sa.String(length=10), nullable=False),
        sa.Column('standard_id', sa.Integer(), nullable=True),
        sa.Column('market_price_cents', sa.Integer(), nullable=True),
        sa.Column('price_source', sa.String(length=200), nullable=True),
        sa.Column('price_reference', sa.String(length=40), nullable=True),
        sa.Column('flat_rate', sa.String(length=12), nullable=True),
        sa.Column('unit_value_cents', sa.Integer(), nullable=True),
        sa.Column('value_cents', sa.Integer(), nullable=True),
        sa.Column('depreciation_cents', sa.Integer(), nullable=True),
        sa.Column('depreciation_reason', sa.String(length=300), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_stock_lines_fiscal_year_id',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], name='fk_stock_lines_account_id', ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['variation_account_id'], ['accounts.id'], name='fk_stock_lines_variation_account_id',
                                ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['standard_id'], ['stock_standards.id'], name='fk_stock_lines_standard_id',
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_stock_lines_fiscal_year_id', 'stock_lines', ['fiscal_year_id'])
    op.create_table(
        'stock_count_files',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('attachment_path', sa.String(length=300), nullable=True),
        sa.Column('attachment_name', sa.String(length=200), nullable=True),
        sa.Column('attachment_mime', sa.String(length=60), nullable=True),
        sa.Column('attachment_size', sa.Integer(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_stock_count_files_fiscal_year_id',
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_stock_count_files_fiscal_year_id', 'stock_count_files', ['fiscal_year_id'])


def downgrade():
    op.drop_index('ix_stock_count_files_fiscal_year_id', table_name='stock_count_files')
    op.drop_table('stock_count_files')
    op.drop_index('ix_stock_lines_fiscal_year_id', table_name='stock_lines')
    op.drop_table('stock_lines')
    op.drop_table('stock_standards')
    op.drop_table('stock_settings')
