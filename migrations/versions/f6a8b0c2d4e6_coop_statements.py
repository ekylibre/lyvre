"""décomptes de coopérative (lot AG10.d)

Revision ID: f6a8b0c2d4e6
Revises: e5f7a9b1c3d5
Create Date: 2026-11-07 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a8b0c2d4e6'
down_revision = 'e5f7a9b1c3d5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'coop_statements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('number', sa.String(length=40), nullable=False),
        sa.Column('statement_date', sa.Date(), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=True),
        sa.Column('status', sa.String(length=8), nullable=False),
        sa.Column('journal_entry_id', sa.Integer(), nullable=True),
        sa.Column('attachment_path', sa.String(length=300), nullable=True),
        sa.Column('attachment_name', sa.String(length=200), nullable=True),
        sa.Column('attachment_mime', sa.String(length=50), nullable=True),
        sa.Column('attachment_size', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['journal_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entity_id', 'number', name='uq_coop_statements_entity_number'),
    )
    op.create_index('ix_coop_statements_entity_id', 'coop_statements', ['entity_id'])
    op.create_table(
        'coop_statement_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('statement_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('quantity_milli', sa.Integer(), nullable=True),
        sa.Column('unit', sa.String(length=20), nullable=True),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('vat_rate_bp', sa.Integer(), nullable=False),
        sa.Column('vat_cents', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=True),
        sa.Column('activity_id', sa.Integer(), nullable=True),
        sa.Column('campaign_year', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['statement_id'], ['coop_statements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_coop_statement_lines_statement_id', 'coop_statement_lines', ['statement_id'])


def downgrade():
    op.drop_index('ix_coop_statement_lines_statement_id', table_name='coop_statement_lines')
    op.drop_table('coop_statement_lines')
    op.drop_index('ix_coop_statements_entity_id', table_name='coop_statements')
    op.drop_table('coop_statements')
