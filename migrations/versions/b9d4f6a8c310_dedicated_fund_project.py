"""fonds dédiés × projets (lot C.5) : projet financé par la ressource affectée

Revision ID: b9d4f6a8c310
Revises: a8c3e5f7b209
Create Date: 2026-10-23 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9d4f6a8c310'
down_revision = 'a8c3e5f7b209'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('dedicated_funds', schema=None) as batch_op:
        batch_op.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_dedicated_funds_project', 'projects', ['project_id'], ['id'], ondelete='SET NULL')


def downgrade():
    with op.batch_alter_table('dedicated_funds', schema=None) as batch_op:
        batch_op.drop_constraint('fk_dedicated_funds_project', type_='foreignkey')
        batch_op.drop_column('project_id')
