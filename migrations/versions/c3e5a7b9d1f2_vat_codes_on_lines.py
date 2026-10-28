"""lot T2 : code et base de TVA sur les lignes d'écriture, régime TVA des tiers, achats et ventes

Revision ID: c3e5a7b9d1f2
Revises: b2d4f6a8c0e1
Create Date: 2026-10-27 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3e5a7b9d1f2'
down_revision = 'b2d4f6a8c0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('journal_lines') as batch_op:
        batch_op.add_column(sa.Column('vat_code', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('vat_base_cents', sa.Integer(), nullable=True))
        batch_op.create_index('ix_journal_lines_vat_code', ['vat_code'])
    with op.batch_alter_table('entities') as batch_op:
        batch_op.add_column(sa.Column('vat_regime', sa.String(length=8), nullable=False, server_default='fr'))
    with op.batch_alter_table('purchases') as batch_op:
        batch_op.add_column(sa.Column('vat_regime', sa.String(length=8), nullable=True))
    with op.batch_alter_table('sales') as batch_op:
        batch_op.add_column(sa.Column('vat_regime', sa.String(length=8), nullable=True))


def downgrade():
    with op.batch_alter_table('sales') as batch_op:
        batch_op.drop_column('vat_regime')
    with op.batch_alter_table('purchases') as batch_op:
        batch_op.drop_column('vat_regime')
    with op.batch_alter_table('entities') as batch_op:
        batch_op.drop_column('vat_regime')
    with op.batch_alter_table('journal_lines') as batch_op:
        batch_op.drop_index('ix_journal_lines_vat_code')
        batch_op.drop_column('vat_base_cents')
        batch_op.drop_column('vat_code')
