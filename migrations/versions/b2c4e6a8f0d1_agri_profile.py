"""profil fiscal daté et forme juridique codée (lot AG1.a, comptabilité agricole)

Revision ID: b2c4e6a8f0d1
Revises: a7c9e1b3d5f2
Create Date: 2026-11-03 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c4e6a8f0d1'
down_revision = 'a7c9e1b3d5f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('organization') as batch_op:
        batch_op.add_column(sa.Column('legal_form_code', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('created_on', sa.Date(), nullable=True))
    with op.batch_alter_table('simple_categories') as batch_op:
        batch_op.add_column(sa.Column('excluded_from_micro', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        'tax_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('value', sa.String(length=30), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('origin', sa.String(length=10), nullable=False, server_default='law'),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tax_profiles_kind', 'tax_profiles', ['kind'])
    op.create_table(
        'tax_options',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=30), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('duration_years', sa.Integer(), nullable=True),
        sa.Column('tacit_renewal', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('renounced_on', sa.Date(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_tax_options_code', 'tax_options', ['code'])


def downgrade():
    op.drop_index('ix_tax_options_code', table_name='tax_options')
    op.drop_table('tax_options')
    op.drop_index('ix_tax_profiles_kind', table_name='tax_profiles')
    op.drop_table('tax_profiles')
    with op.batch_alter_table('simple_categories') as batch_op:
        batch_op.drop_column('excluded_from_micro')
    with op.batch_alter_table('organization') as batch_op:
        batch_op.drop_column('created_on')
        batch_op.drop_column('legal_form_code')
