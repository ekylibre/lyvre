"""listes de contrôle guidées (lot AG9b.e) : étapes cochées

Revision ID: d4e6f8a0b2c4
Revises: c3d5e7f9a1b3
Create Date: 2026-11-06 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e6f8a0b2c4'
down_revision = 'c3d5e7f9a1b3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'checklist_marks',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('checklist_id', sa.String(length=20), nullable=False),
        sa.Column('period', sa.String(length=20), nullable=False),
        sa.Column('step_id', sa.String(length=30), nullable=False),
        sa.Column('done_on', sa.Date(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('checklist_id', 'period', 'step_id', name='uq_checklist_marks_step'),
    )


def downgrade():
    op.drop_table('checklist_marks')
