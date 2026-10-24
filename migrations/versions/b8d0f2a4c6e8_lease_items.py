"""lot L1 : lignes de bail, brouillons, type et révision du bail, gérants, forme juridique

Revision ID: b8d0f2a4c6e8
Revises: a6c8e0f2b4d7
Create Date: 2026-10-25 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b8d0f2a4c6e8'
down_revision = 'a6c8e0f2b4d7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('leases', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(length=10), nullable=False, server_default='active'))
        batch_op.add_column(sa.Column('kind', sa.String(length=12), nullable=True))
        batch_op.add_column(sa.Column('premises_label', sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column('signed_on_place', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('index_code', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('index_reference_period', sa.String(length=10), nullable=True))
        batch_op.add_column(sa.Column('index_reference_value', sa.Numeric(8, 2), nullable=True))
        batch_op.add_column(sa.Column('revision_months', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('next_revision_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('revise_deposit', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        'lease_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lease_id', sa.Integer(), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('letter', sa.String(length=3), nullable=True),
        sa.Column('label', sa.String(length=200), nullable=False),
        sa.Column('nature', sa.String(length=10), nullable=False, server_default='flat'),
        sa.Column('area_m2', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('built_m2', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('billing_unit', sa.String(length=4), nullable=False, server_default='flat'),
        sa.Column('unit_price_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('annual_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cadastral_refs', sa.JSON(), nullable=True),
        sa.Column('geometry', sa.JSON(), nullable=True),
        sa.Column('source', sa.String(length=10), nullable=False, server_default='manual'),
        sa.Column('partial', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(['lease_id'], ['leases.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_lease_items_lease_id', 'lease_items', ['lease_id'])
    with op.batch_alter_table('associates', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_manager', sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table('organization', schema=None) as batch_op:
        batch_op.add_column(sa.Column('legal_form', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('rcs_city', sa.String(length=100), nullable=True))
    # Baux existants : une ligne forfaitaire, loyer annuel = loyer d'échéance × échéances par an.
    op.execute(
        "INSERT INTO lease_items (lease_id, position, label, nature, billing_unit, unit_price_cents, annual_cents) "
        "SELECT l.id, 0, l.unit_label, 'flat', 'flat', "
        "l.rent_cents * CASE r.frequency WHEN 'quarterly' THEN 4 WHEN 'yearly' THEN 1 ELSE 12 END, "
        "l.rent_cents * CASE r.frequency WHEN 'quarterly' THEN 4 WHEN 'yearly' THEN 1 ELSE 12 END "
        "FROM leases l LEFT JOIN recurrences r ON r.id = l.recurrence_id"
    )


def downgrade():
    with op.batch_alter_table('organization', schema=None) as batch_op:
        batch_op.drop_column('rcs_city')
        batch_op.drop_column('legal_form')
    with op.batch_alter_table('associates', schema=None) as batch_op:
        batch_op.drop_column('is_manager')
    op.drop_index('ix_lease_items_lease_id', table_name='lease_items')
    op.drop_table('lease_items')
    with op.batch_alter_table('leases', schema=None) as batch_op:
        for column in ('revise_deposit', 'next_revision_date', 'revision_months', 'index_reference_value',
                       'index_reference_period', 'index_code', 'signed_on_place', 'premises_label', 'kind', 'status'):
            batch_op.drop_column(column)
