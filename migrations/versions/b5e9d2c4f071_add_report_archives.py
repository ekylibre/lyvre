"""add report_archives

Revision ID: b5e9d2c4f071
Revises: a4d8f1e6c903
Create Date: 2026-06-28 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b5e9d2c4f071'
down_revision = 'a4d8f1e6c903'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'report_archives',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=200), nullable=True),
        sa.Column('path', sa.String(length=300), nullable=False),
        sa.Column('prorata', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('created_by_user_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fiscal_year_id', 'version', name='uq_report_archive'),
    )
    with op.batch_alter_table('report_archives', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_report_archives_fiscal_year_id'), ['fiscal_year_id'], unique=False)


def downgrade():
    with op.batch_alter_table('report_archives', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_report_archives_fiscal_year_id'))
    op.drop_table('report_archives')
