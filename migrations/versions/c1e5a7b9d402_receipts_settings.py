"""reçus fiscaux (lot B.1) : adresse et nature des tiers, paramètres des reçus

Revision ID: c1e5a7b9d402
Revises: b9d4f6a8c310
Create Date: 2026-10-24 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1e5a7b9d402'
down_revision = 'b9d4f6a8c310'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.add_column(sa.Column('address_line1', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('address_line2', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('postal_code', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('city', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('country', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('person_kind', sa.String(length=12), nullable=True))
    op.create_table(
        'receipt_settings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('eligibility', sa.String(length=20), nullable=True),
        sa.Column('eligibility_detail', sa.Text(), nullable=True),
        sa.Column('rescrit_ref', sa.String(length=100), nullable=True),
        sa.Column('cgi_articles_json', sa.Text(), nullable=True),
        sa.Column('donation_prefixes_json', sa.Text(), nullable=True),
        sa.Column('default_mode', sa.String(length=10), server_default='annual', nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(), nullable=True),
        sa.Column('acknowledged_by_user_id', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('receipt_settings')
    with op.batch_alter_table('entities', schema=None) as batch_op:
        for column in ('person_kind', 'country', 'city', 'postal_code', 'address_line2', 'address_line1'):
            batch_op.drop_column(column)
