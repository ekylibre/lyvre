"""échéancier de l'exploitation (lot AG9a.d) : abonnements au résumé du lundi

Revision ID: c9d1f3b5e7a8
Revises: b8c0e2a4f6d7
Create Date: 2026-11-04 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d1f3b5e7a8'
down_revision = 'b8c0e2a4f6d7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'agenda_subscriptions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('subscribed', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('last_sent_week', sa.String(length=8), nullable=True),
        sa.Column('last_sent_at', sa.DateTime(), nullable=True),
        sa.Column('ical_token', sa.String(length=64), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', name='uq_agenda_subscriptions_user_id'),
        sa.UniqueConstraint('ical_token', name='uq_agenda_subscriptions_ical_token'),
    )


def downgrade():
    op.drop_table('agenda_subscriptions')
