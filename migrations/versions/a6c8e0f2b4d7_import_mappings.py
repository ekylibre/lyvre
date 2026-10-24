"""lot F6 : reprise d'historique (correspondances de comptes, profils d'import tableur)

Revision ID: a6c8e0f2b4d7
Revises: f5b7c9d1e3a5
Create Date: 2026-10-24 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a6c8e0f2b4d7'
down_revision = 'f5b7c9d1e3a5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'account_mappings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_code', sa.String(length=80), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_code', name='uq_account_mappings_source_code'),
    )
    op.create_table(
        'import_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('columns_json', sa.Text(), nullable=False),
        sa.Column('options_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_import_profiles_name'),
    )


def downgrade():
    op.drop_table('import_profiles')
    op.drop_table('account_mappings')
