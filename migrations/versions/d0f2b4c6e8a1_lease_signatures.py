"""lot L4 : signature électronique des baux (Docuseal)

Revision ID: d0f2b4c6e8a1
Revises: c9e1a3b5d7f9
Create Date: 2026-10-25 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd0f2b4c6e8a1'
down_revision = 'c9e1a3b5d7f9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'lease_signatures',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lease_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(length=20), nullable=False, server_default='docuseal'),
        sa.Column('submission_id', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='sent'),
        sa.Column('sent_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('checked_at', sa.DateTime(), nullable=True),
        sa.Column('sent_pdf_path', sa.String(length=300), nullable=True),
        sa.Column('signed_pdf_path', sa.String(length=300), nullable=True),
        sa.Column('audit_pdf_path', sa.String(length=300), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['lease_id'], ['leases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lease_signatures_lease_id', 'lease_signatures', ['lease_id'])
    op.create_table(
        'lease_signers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('signature_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('role', sa.String(length=60), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('email', sa.String(length=200), nullable=False),
        sa.Column('associate_id', sa.Integer(), nullable=True),
        sa.Column('entity_id', sa.Integer(), nullable=True),
        sa.Column('submitter_id', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='awaiting'),
        sa.Column('signed_at', sa.DateTime(), nullable=True),
        sa.Column('declined_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['signature_id'], ['lease_signatures.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lease_signers_signature_id', 'lease_signers', ['signature_id'])


def downgrade():
    op.drop_index('ix_lease_signers_signature_id', table_name='lease_signers')
    op.drop_table('lease_signers')
    op.drop_index('ix_lease_signatures_lease_id', table_name='lease_signatures')
    op.drop_table('lease_signatures')
