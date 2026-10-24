"""lot F1 : validation des écritures par lots, historique des écritures

Reprise : les écritures déjà numérotées (clôture provisoire) forment un lot « migration » par
exercice ; dans les exercices ouverts, les écritures des factures et avoirs de vente émis sont
validées d'office (décision CO7), numérotées à la suite par journal.

Revision ID: b1d3f5a7c9e2
Revises: a8c0e2f4b6d9
Create Date: 2026-10-24 12:00:00.000000

"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1d3f5a7c9e2'
down_revision = 'a8c0e2f4b6d9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'validation_batches',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('until_date', sa.Date(), nullable=True),
        sa.Column('entries', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.Column('undone_at', sa.DateTime(), nullable=True),
        sa.Column('undone_by', sa.Integer(), nullable=True),
        sa.Column('undo_reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_validation_batches_fiscal_year_id', 'validation_batches', ['fiscal_year_id'])
    op.create_table(
        'entry_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('entry_id', sa.Integer(), nullable=True),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=True),
        sa.Column('reference', sa.String(length=50), nullable=True),
        sa.Column('action', sa.String(length=12), nullable=False),
        sa.Column('snapshot_json', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('origin', sa.String(length=60), nullable=True),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_entry_events_entry_id', 'entry_events', ['entry_id'])
    op.create_index('ix_entry_events_fiscal_year_id', 'entry_events', ['fiscal_year_id'])
    with op.batch_alter_table('journal_entries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('validation_batch_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_journal_entries_validation_batch', 'validation_batches',
                                    ['validation_batch_id'], ['id'], ondelete='SET NULL')

    conn = op.get_bind()
    now = datetime.utcnow()
    years = conn.execute(sa.text("SELECT id, closed FROM fiscal_years ORDER BY start_date")).fetchall()
    for fy_id, closed in years:
        numbered = conn.execute(sa.text(
            "SELECT COUNT(*), MIN(validated_at) FROM journal_entries "
            "WHERE fiscal_year_id = :fy AND validation_number IS NOT NULL"), {"fy": fy_id}).fetchone()
        if numbered[0]:
            batch = _batch(conn, fy_id, numbered[0], numbered[1] or now)
            conn.execute(sa.text("UPDATE journal_entries SET validation_batch_id = :b "
                                 "WHERE fiscal_year_id = :fy AND validation_number IS NOT NULL"),
                         {"b": batch, "fy": fy_id})
        if closed:
            continue
        sales = conn.execute(sa.text(
            "SELECT id, journal_id FROM journal_entries WHERE fiscal_year_id = :fy AND source = 'SALE' "
            "AND validation_number IS NULL ORDER BY journal_id, entry_date, id"), {"fy": fy_id}).fetchall()
        if not sales:
            continue
        batch = _batch(conn, fy_id, len(sales), now)
        counters = {}
        for entry_id, journal_id in sales:
            if journal_id not in counters:
                counters[journal_id] = conn.execute(sa.text(
                    "SELECT COALESCE(MAX(validation_number), 0) FROM journal_entries "
                    "WHERE fiscal_year_id = :fy AND journal_id = :j"), {"fy": fy_id, "j": journal_id}).scalar()
            counters[journal_id] += 1
            conn.execute(sa.text("UPDATE journal_entries SET validation_number = :n, validated_at = :at, "
                                 "validation_batch_id = :b WHERE id = :id"),
                         {"n": counters[journal_id], "at": now, "b": batch, "id": entry_id})


def _batch(conn, fy_id, count, at):
    conn.execute(sa.text("INSERT INTO validation_batches (fiscal_year_id, kind, entries, at) "
                         "VALUES (:fy, 'migration', :n, :at)"), {"fy": fy_id, "n": count, "at": at})
    return conn.execute(sa.text("SELECT MAX(id) FROM validation_batches")).scalar()


def downgrade():
    with op.batch_alter_table('journal_entries', schema=None) as batch_op:
        batch_op.drop_constraint('fk_journal_entries_validation_batch', type_='foreignkey')
        batch_op.drop_column('validation_batch_id')
    op.drop_index('ix_entry_events_fiscal_year_id', table_name='entry_events')
    op.drop_index('ix_entry_events_entry_id', table_name='entry_events')
    op.drop_table('entry_events')
    op.drop_index('ix_validation_batches_fiscal_year_id', table_name='validation_batches')
    op.drop_table('validation_batches')
