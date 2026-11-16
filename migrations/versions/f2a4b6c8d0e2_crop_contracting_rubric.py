"""avances aux cultures (lot CG2.a) : travaux par des tiers (6051) dans leur propre rubrique, exercices ouverts

Revision ID: f2a4b6c8d0e2
Revises: e1f3a5b7c9d1
Create Date: 2026-11-07 23:00:00.000000

Les charges rattachées à une ligne d'écriture 6051… passent de « machinery » à « contracting » : en M1 et M2, elles sont
désormais prises au coût réel (claudedocs/design_fiabilisation_cegara.md § 2.1). Les exercices clôturés ne changent pas :
leur valeur d'inventaire est figée.
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'f2a4b6c8d0e2'
down_revision = 'e1f3a5b7c9d1'
branch_labels = None
depends_on = None

_OPEN_COSTS_6051 = """
    SELECT c.id FROM crop_advance_costs c
    JOIN crop_advances a ON a.id = c.crop_advance_id
    JOIN fiscal_years fy ON fy.id = a.fiscal_year_id
    JOIN journal_lines l ON l.id = c.journal_line_id
    JOIN accounts acc ON acc.id = l.account_id
    WHERE fy.status = 'open' AND acc.code LIKE '6051%'
"""


def upgrade():
    op.execute(f"UPDATE crop_advance_costs SET rubric = 'contracting' "
               f"WHERE rubric = 'machinery' AND id IN ({_OPEN_COSTS_6051})")


def downgrade():
    op.execute("UPDATE crop_advance_costs SET rubric = 'machinery' WHERE rubric = 'contracting'")
