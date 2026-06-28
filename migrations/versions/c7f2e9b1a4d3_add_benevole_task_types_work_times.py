"""add benevole, task_types, work_times

Revision ID: c7f2e9b1a4d3
Revises: b3e1a7c2d9f4
Create Date: 2026-06-27 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7f2e9b1a4d3'
down_revision = 'b3e1a7c2d9f4'
branch_labels = None
depends_on = None


def upgrade():
    # --- entities.is_benevole -------------------------------------------------
    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                'is_benevole',
                sa.Boolean(),
                nullable=False,
                server_default=sa.text('false'),
            )
        )

    # --- task_types -----------------------------------------------------------
    op.create_table(
        'task_types',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('hourly_rate_cents', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False,
                  server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('task_types', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_task_types_name'), ['name'], unique=True
        )

    # --- work_times -----------------------------------------------------------
    op.create_table(
        'work_times',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('task_type_id', sa.Integer(), nullable=False),
        sa.Column('work_date', sa.Date(), nullable=False),
        sa.Column('hours', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_type_id'], ['task_types.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('work_times', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_work_times_entity_id'), ['entity_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_work_times_task_type_id'), ['task_type_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_work_times_work_date'), ['work_date'], unique=False
        )


def downgrade():
    with op.batch_alter_table('work_times', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_work_times_work_date'))
        batch_op.drop_index(batch_op.f('ix_work_times_task_type_id'))
        batch_op.drop_index(batch_op.f('ix_work_times_entity_id'))
    op.drop_table('work_times')

    with op.batch_alter_table('task_types', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_types_name'))
    op.drop_table('task_types')

    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.drop_column('is_benevole')
