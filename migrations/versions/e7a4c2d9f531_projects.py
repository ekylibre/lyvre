"""projets (lot C.1) : axe analytique unique sur les lignes d'écriture, d'achat et les règles

Revision ID: e7a4c2d9f531
Revises: d5f3b8e1a426
Create Date: 2026-10-23 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7a4c2d9f531'
down_revision = 'd5f3b8e1a426'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('manager', sa.String(length=120), nullable=True),
        sa.Column('archived', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    with op.batch_alter_table('journal_lines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_journal_lines_project', 'projects', ['project_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_journal_lines_project_id', ['project_id'])
    for table in ('purchase_lines', 'rules'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.add_column(sa.Column('project_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(f'fk_{table}_project', 'projects', ['project_id'], ['id'], ondelete='SET NULL')


def downgrade():
    for table in ('rules', 'purchase_lines'):
        with op.batch_alter_table(table, schema=None) as batch_op:
            batch_op.drop_constraint(f'fk_{table}_project', type_='foreignkey')
            batch_op.drop_column('project_id')
    with op.batch_alter_table('journal_lines', schema=None) as batch_op:
        batch_op.drop_index('ix_journal_lines_project_id')
        batch_op.drop_constraint('fk_journal_lines_project', type_='foreignkey')
        batch_op.drop_column('project_id')
    op.drop_table('projects')
