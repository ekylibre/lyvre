"""MSA (lot AG7.a) : exploitants suivis, assiettes sociales, lignes saisies du passage

Revision ID: b6c8d0e2f4a6
Revises: a5b7c9d1e3f5
Create Date: 2026-11-05 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b6c8d0e2f4a6'
down_revision = 'a5b7c9d1e3f5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'msa_people',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('associate_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False, server_default='principal'),
        sa.Column('base_option', sa.String(length=10), nullable=False, server_default='triennial'),
        sa.Column('option_since', sa.Date(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['associate_id'], ['associates.id'], name='fk_msa_people_associate_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('associate_id', name='uq_msa_people_associate_id'),
    )
    op.create_table(
        'msa_bases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=False),
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=8), nullable=False),
        sa.Column('income_cents', sa.Integer(), nullable=True),
        sa.Column('abatement_cents', sa.Integer(), nullable=True),
        sa.Column('base_cents', sa.Integer(), nullable=False),
        sa.Column('detail_json', sa.Text(), nullable=True),
        sa.Column('note', sa.String(length=300), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['person_id'], ['msa_people.id'], name='fk_msa_bases_person_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('person_id', 'year', name='uq_msa_bases_person_year'),
    )
    with op.batch_alter_table('msa_bases') as batch:
        batch.create_index('ix_msa_bases_person_id', ['person_id'])
    op.create_table(
        'msa_adjustments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_year_id', sa.Integer(), nullable=False),
        sa.Column('person_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=10), nullable=False),
        sa.Column('amount_cents', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(length=300), nullable=True),
        sa.ForeignKeyConstraint(['fiscal_year_id'], ['fiscal_years.id'], name='fk_msa_adjustments_fiscal_year_id', ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['person_id'], ['msa_people.id'], name='fk_msa_adjustments_person_id', ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('msa_adjustments') as batch:
        batch.create_index('ix_msa_adjustments_fiscal_year_id', ['fiscal_year_id'])


def downgrade():
    with op.batch_alter_table('msa_adjustments') as batch:
        batch.drop_index('ix_msa_adjustments_fiscal_year_id')
    op.drop_table('msa_adjustments')
    with op.batch_alter_table('msa_bases') as batch:
        batch.drop_index('ix_msa_bases_person_id')
    op.drop_table('msa_bases')
    op.drop_table('msa_people')
