"""clés d'API : journal des appels, origine et vérification des objets créés par un agent (lot AK3)

Revision ID: a2c4e6f8b1d3
Revises: f1a3c5e7b9d2
Create Date: 2026-11-08 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a2c4e6f8b1d3'
down_revision = 'f1a3c5e7b9d2'
branch_labels = None
depends_on = None

TABLES = ('purchases', 'entities', 'journal_entries')
CHECKED = ('purchases', 'entities')


def upgrade():
    op.create_table(
        'api_calls',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('key_id', sa.Integer(), nullable=False),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.Column('channel', sa.String(length=4), nullable=False),
        sa.Column('target', sa.String(length=80), nullable=False),
        sa.Column('domain', sa.String(length=20), nullable=True),
        sa.Column('access', sa.String(length=5), nullable=True),
        sa.Column('status', sa.Integer(), nullable=False),
        sa.Column('error', sa.String(length=300), nullable=True),
        sa.Column('object_type', sa.String(length=20), nullable=True),
        sa.Column('object_id', sa.Integer(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=80), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.UniqueConstraint('key_id', 'idempotency_key', name='uq_api_calls_idempotency'),
    )
    op.create_index('ix_api_calls_key_id', 'api_calls', ['key_id'])
    op.create_index('ix_api_calls_at', 'api_calls', ['at'])
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column('origin_key_id', sa.Integer(), nullable=True))
            batch.add_column(sa.Column('origin_label', sa.String(length=80), nullable=True))
            batch.add_column(sa.Column('external_ref', sa.String(length=120), nullable=True))
            if table in CHECKED:
                batch.add_column(sa.Column('checked_at', sa.DateTime(), nullable=True))
                batch.add_column(sa.Column('checked_by_id', sa.Integer(), nullable=True))
            batch.create_index(f'ix_{table}_origin_key_id', ['origin_key_id'])
            batch.create_index(f'ix_{table}_external_ref', ['external_ref'])


def downgrade():
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_index(f'ix_{table}_external_ref')
            batch.drop_index(f'ix_{table}_origin_key_id')
            if table in CHECKED:
                batch.drop_column('checked_by_id')
                batch.drop_column('checked_at')
            batch.drop_column('external_ref')
            batch.drop_column('origin_label')
            batch.drop_column('origin_key_id')
    op.drop_index('ix_api_calls_at', 'api_calls')
    op.drop_index('ix_api_calls_key_id', 'api_calls')
    op.drop_table('api_calls')
