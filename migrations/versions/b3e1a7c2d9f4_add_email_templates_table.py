"""add email_templates table and seed membership reminder

Revision ID: b3e1a7c2d9f4
Revises: 44b403feb1e1
Create Date: 2026-06-25 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3e1a7c2d9f4'
down_revision = '44b403feb1e1'
branch_labels = None
depends_on = None


DEFAULT_REMINDER_SUBJECT = "Votre adhésion arrive à échéance"
DEFAULT_REMINDER_BODY = """\
<p>Bonjour {{ nom }},</p>

<p>Votre adhésion est arrivée à échéance le {{ date_anniversaire }}.</p>

<p>Pour continuer à soutenir l'association, vous pouvez renouveler votre
adhésion en quelques clics :</p>

<p><a href="{{ lien_helloasso }}">Renouveler mon adhésion</a></p>

<p>Merci pour votre soutien,<br>
L'équipe de l'association</p>
"""


def upgrade():
    op.create_table(
        'email_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=50), nullable=False),
        sa.Column('subject', sa.String(length=300), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )
    email_templates = sa.table(
        'email_templates',
        sa.column('key', sa.String),
        sa.column('subject', sa.String),
        sa.column('body_html', sa.Text),
    )
    op.bulk_insert(email_templates, [{
        'key': 'membership_reminder',
        'subject': DEFAULT_REMINDER_SUBJECT,
        'body_html': DEFAULT_REMINDER_BODY,
    }])


def downgrade():
    op.drop_table('email_templates')
