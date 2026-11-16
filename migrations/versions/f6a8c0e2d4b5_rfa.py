"""remboursement forfaitaire agricole (lot AG2.e, 3520) : classes de taux, clients, attestations, demandes

Revision ID: f6a8c0e2d4b5
Revises: e5f7b9d1c3a4
Create Date: 2026-11-04 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a8c0e2d4b5'
down_revision = 'e5f7b9d1c3a4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('simple_categories') as batch_op:
        batch_op.add_column(sa.Column('rfa_rate', sa.String(length=10), nullable=True))
    with op.batch_alter_table('products') as batch_op:
        batch_op.add_column(sa.Column('rfa_rate', sa.String(length=10), nullable=True))
    with op.batch_alter_table('entities') as batch_op:
        batch_op.add_column(sa.Column('rfa_buyer', sa.String(length=12), nullable=True))
    op.create_table(
        'rfa_attestations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('received_on', sa.Date(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('attachment_path', sa.String(length=300), nullable=True),
        sa.Column('attachment_name', sa.String(length=200), nullable=True),
        sa.Column('attachment_mime', sa.String(length=60), nullable=True),
        sa.Column('attachment_size', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['entity_id'], ['entities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('entity_id', 'year', name='uq_rfa_attestations_entity_year'),
    )
    op.create_index('ix_rfa_attestations_entity_id', 'rfa_attestations', ['entity_id'])
    op.create_table(
        'rfa_claims',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='declared'),
        sa.Column('high_base_cents', sa.Integer(), nullable=False),
        sa.Column('low_base_cents', sa.Integer(), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('detail_json', sa.Text(), nullable=False),
        sa.Column('declared_on', sa.Date(), nullable=False),
        sa.Column('refunded_on', sa.Date(), nullable=True),
        sa.Column('entry_id', sa.Integer(), nullable=True),
        sa.Column('declared_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('year'),
    )


def downgrade():
    op.drop_table('rfa_claims')
    op.drop_index('ix_rfa_attestations_entity_id', table_name='rfa_attestations')
    op.drop_table('rfa_attestations')
    with op.batch_alter_table('entities') as batch_op:
        batch_op.drop_column('rfa_buyer')
    with op.batch_alter_table('products') as batch_op:
        batch_op.drop_column('rfa_rate')
    with op.batch_alter_table('simple_categories') as batch_op:
        batch_op.drop_column('rfa_rate')
