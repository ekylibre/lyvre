"""analytique agricole (lot AG8.e) : clé de répartition des activités auxiliaires, état des marges figé

Revision ID: b2c4d6e8f0a2
Revises: a1b3c5d7e9f1
Create Date: 2026-11-06 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c4d6e8f0a2'
down_revision = 'a1b3c5d7e9f1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('activities') as batch:
        batch.add_column(sa.Column('distribution_key_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_activities_distribution_key_id', 'analytic_keys', ['distribution_key_id'], ['id'], ondelete='SET NULL')
    op.create_table(
        'analytic_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('snapshot_json', sa.Text(), nullable=False),
        sa.Column('frozen_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_analytic_snapshots_fiscal_year_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fiscal_year_id', name='uq_analytic_snapshots_fiscal_year_id'),
    )


def downgrade():
    op.drop_table('analytic_snapshots')
    with op.batch_alter_table('activities') as batch:
        batch.drop_constraint('fk_activities_distribution_key_id', type_='foreignkey')
        batch.drop_column('distribution_key_id')
