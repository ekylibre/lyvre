"""add eco_declarations, report_contents, report_assets

Revision ID: a4d8f1e6c903
Revises: e2a9c4d77b51
Create Date: 2026-06-28 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a4d8f1e6c903'
down_revision = 'e2a9c4d77b51'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'eco_declarations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('organism', sa.String(length=20), nullable=False),
        sa.Column('material', sa.String(length=40), nullable=False),
        sa.Column('quarter_label', sa.String(length=10), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('entrant_t', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('sortant_t', sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column('financing_cents', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False, server_default='import'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organism', 'material', 'quarter_label', name='uq_eco_declaration'),
    )
    with op.batch_alter_table('eco_declarations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_eco_declarations_organism'), ['organism'], unique=False)
        batch_op.create_index(batch_op.f('ix_eco_declarations_period_start'), ['period_start'], unique=False)

    op.create_table(
        'report_contents',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('block_key', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=True),
        sa.Column('body_html', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fiscal_year_id', 'block_key', name='uq_report_content'),
    )
    with op.batch_alter_table('report_contents', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_report_contents_fiscal_year_id'), ['fiscal_year_id'], unique=False)

    op.create_table(
        'report_assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('slot', sa.String(length=50), nullable=False),
        sa.Column('path', sa.String(length=300), nullable=False),
        sa.Column('caption', sa.String(length=300), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('report_assets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_report_assets_fiscal_year_id'), ['fiscal_year_id'], unique=False)


def downgrade():
    with op.batch_alter_table('report_assets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_report_assets_fiscal_year_id'))
    op.drop_table('report_assets')

    with op.batch_alter_table('report_contents', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_report_contents_fiscal_year_id'))
    op.drop_table('report_contents')

    with op.batch_alter_table('eco_declarations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_eco_declarations_period_start'))
        batch_op.drop_index(batch_op.f('ix_eco_declarations_organism'))
    op.drop_table('eco_declarations')
