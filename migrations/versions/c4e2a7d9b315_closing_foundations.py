"""clôture (lot A.2) : identité de la structure, statut d'exercice, validation des écritures,
étapes et journal de l'assistant de clôture

Revision ID: c4e2a7d9b315
Revises: b7d3e5f1a204
Create Date: 2026-10-22 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4e2a7d9b315'
down_revision = 'b7d3e5f1a204'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'organization',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('siren', sa.String(length=9), nullable=True),
        sa.Column('rna', sa.String(length=10), nullable=True),
        sa.Column('address_line1', sa.String(length=200), nullable=True),
        sa.Column('address_line2', sa.String(length=200), nullable=True),
        sa.Column('postal_code', sa.String(length=10), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('country', sa.String(length=60), server_default='France', nullable=False),
        sa.Column('purpose', sa.Text(), nullable=True),
        sa.Column('signatory_name', sa.String(length=200), nullable=True),
        sa.Column('signatory_title', sa.String(length=100), nullable=True),
        sa.Column('signature_path', sa.String(length=300), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    with op.batch_alter_table('fiscal_years', schema=None) as batch_op:
        batch_op.add_column(sa.Column('status', sa.String(length=12), server_default='open', nullable=False))
        batch_op.add_column(sa.Column('provisional_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('closed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('closed_by_user_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('fec_sha256', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('fec_path', sa.String(length=300), nullable=True))
        batch_op.add_column(sa.Column('allocation_decided_on', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('allocation_body', sa.String(length=100), nullable=True))
    # Reprise : un exercice « clôturé » (verrou seul) devient une clôture provisoire, réversible
    # par l'administrateur, pour pouvoir passer l'assistant (à-nouveaux, FEC).
    op.execute("UPDATE fiscal_years SET status = 'provisional', provisional_at = CURRENT_TIMESTAMP "
               "WHERE closed = 1")

    with op.batch_alter_table('journal_entries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('validation_number', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('validated_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('reverses_entry_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('inventory_kind', sa.String(length=20), nullable=True))
        batch_op.create_foreign_key('fk_journal_entries_reverses', 'journal_entries', ['reverses_entry_id'], ['id'],
                                    ondelete='SET NULL')
        batch_op.create_index('ix_journal_entries_validation', ['fiscal_year_id', 'journal_id', 'validation_number'],
                              unique=False)

    op.create_table(
        'closing_steps',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('step', sa.String(length=20), nullable=False),
        sa.Column('state', sa.String(length=10), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('fiscal_year_id', 'step', name='uq_closing_step'),
    )
    with op.batch_alter_table('closing_steps', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_closing_steps_fiscal_year_id'), ['fiscal_year_id'], unique=False)

    op.create_table(
        'closing_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('step', sa.String(length=20), nullable=True),
        sa.Column('action', sa.String(length=40), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('at', sa.DateTime(), nullable=False),
        sa.Column('details_json', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('closing_events', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_closing_events_fiscal_year_id'), ['fiscal_year_id'], unique=False)


def downgrade():
    with op.batch_alter_table('closing_events', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_closing_events_fiscal_year_id'))
    op.drop_table('closing_events')
    with op.batch_alter_table('closing_steps', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_closing_steps_fiscal_year_id'))
    op.drop_table('closing_steps')

    with op.batch_alter_table('journal_entries', schema=None) as batch_op:
        batch_op.drop_index('ix_journal_entries_validation')
        batch_op.drop_constraint('fk_journal_entries_reverses', type_='foreignkey')
        batch_op.drop_column('inventory_kind')
        batch_op.drop_column('reverses_entry_id')
        batch_op.drop_column('validated_at')
        batch_op.drop_column('validation_number')

    with op.batch_alter_table('fiscal_years', schema=None) as batch_op:
        for column in ('allocation_body', 'allocation_decided_on', 'fec_path', 'fec_sha256', 'closed_by_user_id',
                       'closed_at', 'provisional_at', 'status'):
            batch_op.drop_column(column)

    op.drop_table('organization')
