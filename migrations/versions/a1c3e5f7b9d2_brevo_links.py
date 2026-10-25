"""lot B2 : liens adhérent ↔ contact Brevo

Revision ID: a1c3e5f7b9d2
Revises: f3b5d7e9a1c4
Create Date: 2026-10-26 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1c3e5f7b9d2'
down_revision = 'f3b5d7e9a1c4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'brevo_links',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('contact_id', sa.BigInteger(), nullable=False),
        sa.Column('email', sa.String(length=200), nullable=True),
        sa.Column('payload_hash', sa.String(length=64), nullable=True),
        sa.Column('in_list', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('state', sa.String(length=12), nullable=False, server_default='linked'),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entity_id', name='uq_brevo_links_entity'),
        sa.UniqueConstraint('contact_id', name='uq_brevo_links_contact'),
    )


def downgrade():
    op.drop_table('brevo_links')
