"""lot L2 : modèles de bail, texte du bail

Revision ID: c9e1a3b5d7f9
Revises: b8d0f2a4c6e8
Create Date: 2026-10-25 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9e1a3b5d7f9'
down_revision = 'b8d0f2a4c6e8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'lease_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('reviewed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('kind'),
    )
    with op.batch_alter_table('leases', schema=None) as batch_op:
        batch_op.add_column(sa.Column('document_html', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('document_generated_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('document_edited', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('leases', schema=None) as batch_op:
        batch_op.drop_column('document_edited')
        batch_op.drop_column('document_generated_at')
        batch_op.drop_column('document_html')
    op.drop_table('lease_templates')
