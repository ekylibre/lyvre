"""purchase entry: supplier SIRET, invoice attachment, Qonto upload, non-Qonto payments

Revision ID: 9c41b7e2d5a8
Revises: 24e66976825c
Create Date: 2026-10-22 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c41b7e2d5a8'
down_revision = '24e66976825c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.add_column(sa.Column('siret', sa.String(length=14), nullable=True))
        batch_op.create_index(batch_op.f('ix_entities_siret'), ['siret'], unique=False)

    with op.batch_alter_table('purchases', schema=None) as batch_op:
        batch_op.add_column(sa.Column('supplier_siret', sa.String(length=14), nullable=True))
        batch_op.add_column(sa.Column('attachment_path', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('attachment_name', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('attachment_mime', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('attachment_size', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('idempotency_key', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('qonto_upload_status', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('qonto_upload_error', sa.Text(), nullable=True))

    with op.batch_alter_table('purchase_payments', schema=None) as batch_op:
        batch_op.alter_column('qonto_transaction_id', existing_type=sa.String(length=36),
                              nullable=True)
        batch_op.add_column(sa.Column('origin', sa.String(length=10), server_default='qonto',
                                      nullable=False))
        batch_op.create_unique_constraint('uq_purchase_payment_bank_transaction',
                                          ['purchase_id', 'bank_transaction_id'])


def downgrade():
    # Les liens hors Qonto n'ont pas d'identifiant Qonto : ils disparaissent.
    op.execute("DELETE FROM purchase_payments WHERE qonto_transaction_id IS NULL")
    with op.batch_alter_table('purchase_payments', schema=None) as batch_op:
        batch_op.drop_constraint('uq_purchase_payment_bank_transaction', type_='unique')
        batch_op.drop_column('origin')
        batch_op.alter_column('qonto_transaction_id', existing_type=sa.String(length=36),
                              nullable=False)

    with op.batch_alter_table('purchases', schema=None) as batch_op:
        batch_op.drop_column('qonto_upload_error')
        batch_op.drop_column('qonto_upload_status')
        batch_op.drop_column('idempotency_key')
        batch_op.drop_column('attachment_size')
        batch_op.drop_column('attachment_mime')
        batch_op.drop_column('attachment_name')
        batch_op.drop_column('attachment_path')
        batch_op.drop_column('supplier_siret')

    with op.batch_alter_table('entities', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_entities_siret'))
        batch_op.drop_column('siret')
