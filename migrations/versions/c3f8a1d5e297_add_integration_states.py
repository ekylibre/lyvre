"""add integration_states

Revision ID: c3f8a1d5e297
Revises: b5e9d2c4f071
Create Date: 2026-10-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3f8a1d5e297'
down_revision = 'b5e9d2c4f071'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'integration_states',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('service', sa.String(length=30), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('checked_at', sa.DateTime(), nullable=True),
        sa.Column('check_ok', sa.Boolean(), nullable=True),
        sa.Column('check_message', sa.Text(), nullable=True),
        sa.Column('check_duration_ms', sa.Integer(), nullable=True),
        sa.Column('checked_fingerprint', sa.String(length=64), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('service'),
    )


def downgrade():
    op.drop_table('integration_states')
