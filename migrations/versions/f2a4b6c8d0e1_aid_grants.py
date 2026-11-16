"""aides PAC et subventions (lot AG3.d) : octroi, immobilisations financées, reprises des subventions d'investissement

Revision ID: f2a4b6c8d0e1
Revises: e1f3a5b7c9d0
Create Date: 2026-11-05 01:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f2a4b6c8d0e1'
down_revision = 'e1f3a5b7c9d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('aids') as batch_op:
        batch_op.add_column(sa.Column('grant_entry_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_aids_grant_entry_id', 'journal_entries', ['grant_entry_id'], ['id'],
                                    ondelete='SET NULL')
    op.create_table(
        'aid_assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('aid_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['aid_id'], ['aids.id'], name='fk_aid_assets_aid_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], name='fk_aid_assets_asset_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('aid_id', 'asset_id', name='uq_aid_assets_aid_asset'),
    )
    op.create_index('ix_aid_assets_aid_id', 'aid_assets', ['aid_id'])
    op.create_index('ix_aid_assets_asset_id', 'aid_assets', ['asset_id'])
    op.create_table(
        'aid_releases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('aid_id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=True),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=500), nullable=True),
        sa.Column('entry_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['aid_id'], ['aids.id'], name='fk_aid_releases_aid_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_aid_releases_fiscal_year_id',
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id'], name='fk_aid_releases_asset_id', ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['entry_id'], ['journal_entries.id'], name='fk_aid_releases_entry_id', ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_aid_releases_aid_id', 'aid_releases', ['aid_id'])
    op.create_index('ix_aid_releases_fiscal_year_id', 'aid_releases', ['fiscal_year_id'])


def downgrade():
    op.drop_index('ix_aid_releases_fiscal_year_id', table_name='aid_releases')
    op.drop_index('ix_aid_releases_aid_id', table_name='aid_releases')
    op.drop_table('aid_releases')
    op.drop_index('ix_aid_assets_asset_id', table_name='aid_assets')
    op.drop_index('ix_aid_assets_aid_id', table_name='aid_assets')
    op.drop_table('aid_assets')
    with op.batch_alter_table('aids') as batch_op:
        batch_op.drop_constraint('fk_aids_grant_entry_id', type_='foreignkey')
        batch_op.drop_column('grant_entry_id')
