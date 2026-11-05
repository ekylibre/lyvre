"""fiscalité BA (lot AG6.d) : provision 73 A des vaches, catégorie de vaches à l'inventaire, contrat EGALIM

Revision ID: e3f5a7b9c1d2
Revises: d2e4f6a8b0c1
Create Date: 2026-11-05 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e3f5a7b9c1d2'
down_revision = 'd2e4f6a8b0c1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cow_provisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('heads', sa.Integer(), nullable=False),
        sa.Column('value_cents', sa.Integer(), nullable=False),
        sa.Column('detail_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_cow_provisions_fiscal_year_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fiscal_year_id', name='uq_cow_provisions_fiscal_year_id'),
    )
    op.create_table(
        'cow_provision_releases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provision_id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('heads', sa.Integer(), nullable=True),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(['provision_id'], ['cow_provisions.id'], name='fk_cow_provision_releases_provision_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_cow_provision_releases_fiscal_year_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_cow_provision_releases_provision_id', 'cow_provision_releases', ['provision_id'])
    op.create_index('ix_cow_provision_releases_fiscal_year_id', 'cow_provision_releases', ['fiscal_year_id'])
    with op.batch_alter_table('stock_lines') as batch_op:
        batch_op.add_column(sa.Column('cow_category', sa.String(length=8), nullable=True))
    with op.batch_alter_table('fiscal_years') as batch_op:
        batch_op.add_column(sa.Column('egalim_contract', sa.Boolean(), nullable=True))


def downgrade():
    with op.batch_alter_table('fiscal_years') as batch_op:
        batch_op.drop_column('egalim_contract')
    with op.batch_alter_table('stock_lines') as batch_op:
        batch_op.drop_column('cow_category')
    op.drop_index('ix_cow_provision_releases_fiscal_year_id', table_name='cow_provision_releases')
    op.drop_index('ix_cow_provision_releases_provision_id', table_name='cow_provision_releases')
    op.drop_table('cow_provision_releases')
    op.drop_table('cow_provisions')
