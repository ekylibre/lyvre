"""analytique agricole (lot AG8.b) : clés de répartition, ventilations, règles de compte

Revision ID: f0a2b4c6d8e0
Revises: e9f1a3b5c7d9
Create Date: 2026-11-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f0a2b4c6d8e0'
down_revision = 'e9f1a3b5c7d9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'analytic_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('basis', sa.String(length=14), nullable=False),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('archived', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_analytic_keys_name'),
    )
    op.create_table(
        'analytic_key_members',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key_id', sa.Integer(), nullable=False),
        sa.Column('activity_id', sa.Integer(), nullable=False),
        sa.Column('share_bp', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['key_id'], ['analytic_keys.id'], name='fk_analytic_key_members_key_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], name='fk_analytic_key_members_activity_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('analytic_key_members') as batch:
        batch.create_index('ix_analytic_key_members_key_id', ['key_id'])
    op.create_table(
        'analytic_allocations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('journal_line_id', sa.Integer(), nullable=False),
        sa.Column('activity_id', sa.Integer(), nullable=True),
        sa.Column('key_id', sa.Integer(), nullable=True),
        sa.Column('campaign_year', sa.Integer(), nullable=True),
        sa.Column('share_bp', sa.Integer(), nullable=False),
        sa.Column('origin', sa.String(length=10), nullable=False, server_default='manual'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['journal_line_id'], ['journal_lines.id'], name='fk_analytic_allocations_journal_line_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], name='fk_analytic_allocations_activity_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['key_id'], ['analytic_keys.id'], name='fk_analytic_allocations_key_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('analytic_allocations') as batch:
        batch.create_index('ix_analytic_allocations_journal_line_id', ['journal_line_id'])
    op.create_table(
        'analytic_rules',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_prefix', sa.String(length=20), nullable=False),
        sa.Column('activity_id', sa.Integer(), nullable=True),
        sa.Column('key_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['activity_id'], ['activities.id'], name='fk_analytic_rules_activity_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['key_id'], ['analytic_keys.id'], name='fk_analytic_rules_key_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_prefix', name='uq_analytic_rules_account_prefix'),
    )


def downgrade():
    op.drop_table('analytic_rules')
    with op.batch_alter_table('analytic_allocations') as batch:
        batch.drop_index('ix_analytic_allocations_journal_line_id')
    op.drop_table('analytic_allocations')
    with op.batch_alter_table('analytic_key_members') as batch:
        batch.drop_index('ix_analytic_key_members_key_id')
    op.drop_table('analytic_key_members')
    op.drop_table('analytic_keys')
