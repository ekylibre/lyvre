"""budget (lot C.2) : montants prévus par compte, exercice, projet et mois

Revision ID: f2b6d8a3c147
Revises: e7a4c2d9f531
Create Date: 2026-10-23 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2b6d8a3c147'
down_revision = 'e7a4c2d9f531'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'budget_lines',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('month', sa.Integer(), nullable=True),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('budget_lines', schema=None) as batch_op:
        batch_op.create_index('ix_budget_lines_scope', ['fiscal_year_id', 'project_id'])


def downgrade():
    op.drop_table('budget_lines')
