"""aides PAC et subventions (lot AG3.e) : cache des aides publiées par l'ASP (Lexicon cap_beneficiaries)

Revision ID: a3b5c7d9e1f2
Revises: f2a4b6c8d0e1
Create Date: 2026-11-05 02:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3b5c7d9e1f2'
down_revision = 'f2a4b6c8d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cap_published',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('siren', sa.String(length=9), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('feaga_cents', sa.Integer(), nullable=False),
        sa.Column('feader_cents', sa.Integer(), nullable=False),
        sa.Column('cofinanced_cents', sa.Integer(), nullable=False),
        sa.Column('total_cents', sa.Integer(), nullable=False),
        sa.Column('fetched_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('siren', 'year', name='uq_cap_published_siren_year'),
    )


def downgrade():
    op.drop_table('cap_published')
