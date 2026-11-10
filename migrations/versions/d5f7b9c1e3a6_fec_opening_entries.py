"""écritures : les à-nouveaux d'un FEC importé deviennent des écritures d'ouverture (essai de l'interface, 10/11/2026)

Avant, l'historique importé d'un FEC gardait la source FEC_IMPORT pour toutes ses écritures, à-nouveaux compris : les
calculs qui écartent l'ouverture (annexe des biens vivants, TVA, trésorerie, analytique, stocks…) les comptaient comme
des mouvements. Même règle que l'import (fec_import.is_opening) : journal d'à-nouveaux, premier jour de l'exercice,
comptes de bilan seulement. Seule la source change ; les montants et la validation sont intacts.

Revision ID: d5f7b9c1e3a6
Revises: c4e6a8b0d2f5
Create Date: 2026-11-10 09:00:00.000000

"""
from alembic import op


revision = 'd5f7b9c1e3a6'
down_revision = 'c4e6a8b0d2f5'
branch_labels = None
depends_on = None

JOURNALS = "('AN', 'RAN', 'ANO', 'ANX', 'AN0', 'ANOUV', 'ANV')"


def upgrade():
    op.execute(f"""
        UPDATE journal_entries SET source = 'OPENING'
        WHERE source = 'FEC_IMPORT'
          AND journal_id IN (SELECT id FROM journals WHERE UPPER(TRIM(code)) IN {JOURNALS})
          AND entry_date = (SELECT start_date FROM fiscal_years WHERE fiscal_years.id = journal_entries.fiscal_year_id)
          AND NOT EXISTS (SELECT 1 FROM journal_lines l JOIN accounts a ON a.id = l.account_id
                          WHERE l.entry_id = journal_entries.id AND SUBSTR(a.code, 1, 1) NOT IN ('1', '2', '3', '4', '5'))
          AND NOT EXISTS (SELECT 1 FROM journal_entries o WHERE o.fiscal_year_id = journal_entries.fiscal_year_id
                          AND o.source = 'OPENING')
    """)


def downgrade():
    op.execute(f"""
        UPDATE journal_entries SET source = 'FEC_IMPORT'
        WHERE source = 'OPENING' AND source_ref IS NOT NULL AND source_ref NOT LIKE 'FEC:%'
          AND source_ref NOT LIKE 'AN-%'
          AND source_ref LIKE (SELECT code FROM journals WHERE journals.id = journal_entries.journal_id) || '%'
          AND journal_id IN (SELECT id FROM journals WHERE UPPER(TRIM(code)) IN {JOURNALS})
    """)
