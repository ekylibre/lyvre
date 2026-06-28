"""add metric_snapshots and impact_factors tables

Revision ID: e2a9c4d77b51
Revises: c7f2e9b1a4d3
Create Date: 2026-06-27 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2a9c4d77b51'
down_revision = 'c7f2e9b1a4d3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'metric_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('metric_key', sa.String(length=60), nullable=False),
        sa.Column('period_start', sa.Date(), nullable=False),
        sa.Column('granularity', sa.String(length=10), nullable=False,
                  server_default='month'),
        sa.Column('value', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('unit', sa.String(length=20), nullable=False),
        sa.Column('is_manual', sa.Boolean(), nullable=False,
                  server_default=sa.text('false')),
        sa.Column('captured_at', sa.DateTime(), nullable=True),
        sa.Column('entered_by_user_id', sa.Integer(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'metric_key', 'period_start', 'granularity',
                            name='uq_metric_snapshot_key'),
    )
    with op.batch_alter_table('metric_snapshots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_metric_snapshots_source'), ['source'], unique=False)
        batch_op.create_index(batch_op.f('ix_metric_snapshots_metric_key'), ['metric_key'], unique=False)
        batch_op.create_index(batch_op.f('ix_metric_snapshots_period_start'), ['period_start'], unique=False)
        batch_op.create_index('ix_metric_snapshots_key_period', ['metric_key', 'period_start'], unique=False)

    op.create_table(
        'impact_factors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=60), nullable=False),
        sa.Column('value', sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column('unit', sa.String(length=20), nullable=False),
        sa.Column('source_label', sa.String(length=200), nullable=True),
        sa.Column('source_url', sa.String(length=500), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('updated_by_user_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('impact_factors', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_impact_factors_key'), ['key'], unique=True)


def downgrade():
    with op.batch_alter_table('impact_factors', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_impact_factors_key'))
    op.drop_table('impact_factors')

    with op.batch_alter_table('metric_snapshots', schema=None) as batch_op:
        batch_op.drop_index('ix_metric_snapshots_key_period')
        batch_op.drop_index(batch_op.f('ix_metric_snapshots_period_start'))
        batch_op.drop_index(batch_op.f('ix_metric_snapshots_metric_key'))
        batch_op.drop_index(batch_op.f('ix_metric_snapshots_source'))
    op.drop_table('metric_snapshots')
