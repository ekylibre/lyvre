"""inventaire de clôture agricole (lot AG4.c) : avances aux cultures, barèmes de coût standard, charges 72 A

Revision ID: d6e8f0a2b4c5
Revises: c5d7e9f1a3b4
Create Date: 2026-11-05 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd6e8f0a2b4c5'
down_revision = 'c5d7e9f1a3b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'crop_standards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('production', sa.String(length=120), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=300), nullable=True),
        sa.Column('labour_assumption', sa.String(length=200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('production', 'year', name='uq_crop_standards_production_year'),
    )
    op.create_table(
        'crop_standard_rows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('standard_id', sa.Integer(), nullable=False),
        sa.Column('component', sa.String(length=10), nullable=False),
        sa.Column('month', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['standard_id'], ['crop_standards.id'], name='fk_crop_standard_rows_standard_id',
                                ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('standard_id', 'component', 'month', name='uq_crop_standard_rows'),
    )
    op.create_index('ix_crop_standard_rows_standard_id', 'crop_standard_rows', ['standard_id'])
    op.create_table(
        'crop_advances',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('production', sa.String(length=120), nullable=False),
        sa.Column('surface_ha', sa.Numeric(10, 4), nullable=False),
        sa.Column('planted_on', sa.Date(), nullable=False),
        sa.Column('campaign', sa.Integer(), nullable=True),
        sa.Column('cycle', sa.String(length=5), nullable=False),
        sa.Column('plots', sa.String(length=300), nullable=True),
        sa.Column('method', sa.String(length=12), nullable=False),
        sa.Column('crop_standard_id', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_crop_advances_fiscal_year_id',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['crop_standard_id'], ['crop_standards.id'], name='fk_crop_advances_crop_standard_id',
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_crop_advances_fiscal_year_id', 'crop_advances', ['fiscal_year_id'])
    op.create_table(
        'crop_advance_costs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('crop_advance_id', sa.Integer(), nullable=False),
        sa.Column('rubric', sa.String(length=12), nullable=False),
        sa.Column('journal_line_id', sa.Integer(), nullable=True),
        sa.Column('label', sa.String(length=300), nullable=False),
        sa.Column('base_cents', sa.Integer(), nullable=False),
        sa.Column('share_bp', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['crop_advance_id'], ['crop_advances.id'], name='fk_crop_advance_costs_crop_advance_id',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['journal_line_id'], ['journal_lines.id'], name='fk_crop_advance_costs_journal_line_id',
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_crop_advance_costs_crop_advance_id', 'crop_advance_costs', ['crop_advance_id'])
    with op.batch_alter_table('stock_lines') as batch_op:
        batch_op.add_column(sa.Column('crop_advance_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_stock_lines_crop_advance_id', 'crop_advances', ['crop_advance_id'], ['id'],
                                    ondelete='SET NULL')
        batch_op.create_index('ix_stock_lines_crop_advance_id', ['crop_advance_id'])


def downgrade():
    with op.batch_alter_table('stock_lines') as batch_op:
        batch_op.drop_index('ix_stock_lines_crop_advance_id')
        batch_op.drop_constraint('fk_stock_lines_crop_advance_id', type_='foreignkey')
        batch_op.drop_column('crop_advance_id')
    op.drop_index('ix_crop_advance_costs_crop_advance_id', table_name='crop_advance_costs')
    op.drop_table('crop_advance_costs')
    op.drop_index('ix_crop_advances_fiscal_year_id', table_name='crop_advances')
    op.drop_table('crop_advances')
    op.drop_index('ix_crop_standard_rows_standard_id', table_name='crop_standard_rows')
    op.drop_table('crop_standard_rows')
    op.drop_table('crop_standards')
