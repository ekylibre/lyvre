"""lot L5 : indices de révision des loyers, révisions des baux

Revision ID: e2a4c6e8f0b3
Revises: d0f2b4c6e8a1
Create Date: 2026-10-25 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2a4c6e8f0b3'
down_revision = 'd0f2b4c6e8a1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'rent_indices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=10), nullable=False),
        sa.Column('period', sa.String(length=10), nullable=False),
        sa.Column('value', sa.Numeric(8, 2), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False, server_default='manual'),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', 'period', name='uq_rent_indices_code_period'),
    )
    op.create_table(
        'lease_revisions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lease_id', sa.Integer(), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('index_code', sa.String(length=10), nullable=False),
        sa.Column('old_period', sa.String(length=10), nullable=True),
        sa.Column('old_value', sa.Numeric(8, 2), nullable=True),
        sa.Column('new_period', sa.String(length=10), nullable=False),
        sa.Column('new_value', sa.Numeric(8, 2), nullable=True),
        sa.Column('old_annual_cents', sa.Integer(), nullable=True),
        sa.Column('new_annual_cents', sa.Integer(), nullable=True),
        sa.Column('old_deposit_cents', sa.Integer(), nullable=True),
        sa.Column('new_deposit_cents', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='pending'),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('applied_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['lease_id'], ['leases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lease_id', 'due_date', name='uq_lease_revisions_due'),
    )
    op.create_index('ix_lease_revisions_lease_id', 'lease_revisions', ['lease_id'])


def downgrade():
    op.drop_index('ix_lease_revisions_lease_id', table_name='lease_revisions')
    op.drop_table('lease_revisions')
    op.drop_table('rent_indices')
