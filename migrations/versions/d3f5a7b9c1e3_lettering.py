"""lot F3 : lettrage des comptes de tiers, à-nouveaux détaillés, rôles de comptes

Reprise : comptes lettrables selon leur préfixe (40, 41, 42, 43, 441, 45, 467, 468) ; le lettrage
des pièces déjà payées se fait par `scripts/lettering_reprise.py` (ou au premier encaissement).

Revision ID: d3f5a7b9c1e3
Revises: c2e4a6b8d0f1
Create Date: 2026-10-24 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3f5a7b9c1e3'
down_revision = 'c2e4a6b8d0f1'
branch_labels = None
depends_on = None

LETTRABLE_PREFIXES = ("40", "41", "42", "43", "441", "45", "467", "468")


def upgrade():
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lettrable', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        'letterings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(length=6), nullable=False),
        sa.Column('partial', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('balance_cents', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('lettered_on', sa.Date(), nullable=True),
        sa.Column('origin', sa.String(length=12), nullable=False, server_default='manual'),
        sa.Column('document_type', sa.String(length=12), nullable=True),
        sa.Column('document_id', sa.Integer(), nullable=True),
        sa.Column('gap_entry_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['gap_entry_id'], ['journal_entries.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_letterings_account_id', 'letterings', ['account_id'])
    op.create_index('ix_letterings_document', 'letterings', ['document_type', 'document_id'])
    with op.batch_alter_table('journal_lines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lettering_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('carried_from_line_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_journal_lines_lettering', 'letterings', ['lettering_id'], ['id'], ondelete='SET NULL')
        batch_op.create_foreign_key('fk_journal_lines_carried_from', 'journal_lines', ['carried_from_line_id'], ['id'],
                                    ondelete='SET NULL')
        batch_op.create_index('ix_journal_lines_lettering_id', ['lettering_id'])
        batch_op.create_index('ix_journal_lines_carried_from_line_id', ['carried_from_line_id'])
    op.create_table(
        'account_roles',
        sa.Column('role', sa.String(length=40), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('role'),
    )
    with op.batch_alter_table('organization', schema=None) as batch_op:
        batch_op.add_column(sa.Column('lettering_gap_cents', sa.Integer(), nullable=False, server_default='100'))

    conn = op.get_bind()
    for prefix in LETTRABLE_PREFIXES:
        conn.execute(sa.text("UPDATE accounts SET lettrable = 1 WHERE is_header = 0 AND code LIKE :p"),
                     {"p": prefix + "%"})


def downgrade():
    with op.batch_alter_table('organization', schema=None) as batch_op:
        batch_op.drop_column('lettering_gap_cents')
    op.drop_table('account_roles')
    with op.batch_alter_table('journal_lines', schema=None) as batch_op:
        batch_op.drop_index('ix_journal_lines_carried_from_line_id')
        batch_op.drop_index('ix_journal_lines_lettering_id')
        batch_op.drop_constraint('fk_journal_lines_carried_from', type_='foreignkey')
        batch_op.drop_constraint('fk_journal_lines_lettering', type_='foreignkey')
        batch_op.drop_column('carried_from_line_id')
        batch_op.drop_column('lettering_id')
    op.drop_index('ix_letterings_document', table_name='letterings')
    op.drop_index('ix_letterings_account_id', table_name='letterings')
    op.drop_table('letterings')
    with op.batch_alter_table('accounts', schema=None) as batch_op:
        batch_op.drop_column('lettrable')
