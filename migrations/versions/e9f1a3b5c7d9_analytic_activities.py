"""analytique agricole (lot AG8.a) : ateliers, activités, campagnes, productions

Revision ID: e9f1a3b5c7d9
Revises: d8e0f2a4b6c8
Create Date: 2026-11-06 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e9f1a3b5c7d9'
down_revision = 'd8e0f2a4b6c8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'workshops',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('family', sa.String(length=30), nullable=False),
        sa.Column('isacompta_code', sa.String(length=20), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_workshops_name'),
    )
    op.create_table(
        'activities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('workshop_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('lexicon_reference', sa.String(length=80), nullable=True),
        sa.Column('nature', sa.String(length=12), nullable=False, server_default='main'),
        sa.Column('cycle', sa.String(length=10), nullable=False, server_default='annual'),
        sa.Column('unit', sa.String(length=14), nullable=False, server_default='hectare'),
        sa.Column('cycle_start', sa.String(length=5), nullable=False, server_default='01-01'),
        sa.Column('cycle_stop', sa.String(length=5), nullable=False, server_default='12-31'),
        sa.Column('year_offset', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('isacompta_code', sa.String(length=20), nullable=True),
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['workshop_id'], ['workshops.id'], name='fk_activities_workshop_id', ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workshop_id', 'name', name='uq_activities_workshop_name'),
    )
    with op.batch_alter_table('activities') as batch:
        batch.create_index('ix_activities_workshop_id', ['workshop_id'])
    op.create_table(
        'campaigns',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year', name='uq_campaigns_year'),
    )
    op.create_table(
        'activity_productions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('activity_id', sa.Integer(), nullable=False),
        sa.Column('campaign_id', sa.Integer(), nullable=False),
        sa.Column('measure', sa.Numeric(14, 3), nullable=True),
        sa.Column('measure_source', sa.String(length=12), nullable=False, server_default='entered'),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], name='fk_activity_productions_activity_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['campaign_id'], ['campaigns.id'], name='fk_activity_productions_campaign_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('activity_id', 'campaign_id', name='uq_activity_productions_activity_campaign'),
    )
    with op.batch_alter_table('activity_productions') as batch:
        batch.create_index('ix_activity_productions_activity_id', ['activity_id'])


def downgrade():
    with op.batch_alter_table('activity_productions') as batch:
        batch.drop_index('ix_activity_productions_activity_id')
    op.drop_table('activity_productions')
    op.drop_table('campaigns')
    with op.batch_alter_table('activities') as batch:
        batch.drop_index('ix_activities_workshop_id')
    op.drop_table('activities')
    op.drop_table('workshops')
