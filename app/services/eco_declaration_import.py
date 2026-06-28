"""Import de la déclaration éco-organismes (`Declaration Ecoorganismes.xlsx`).

Parse la feuille `Bilan` (matrice matière × trimestre) :
- Bloc tonnages : par organisme (Ecomaison/Ecologic) et matière, lignes
  Entrant / Sortant, valeurs par trimestre.
- Bloc facturation : financement par organisme et par trimestre.

Upsert dans `eco_declarations` sur `(organism, material, quarter_label)`.
La table éditable (vue `/rapport-activite/eco`) sert de filet de sécurité.
Retour : `{"imported": n, "updated": n, "errors": [...]}`.
"""
import re
from datetime import date

import pandas as pd

from app.extensions import db
from app.models import EcoDeclaration

QUARTER_RE = re.compile(r"^T([1-4])\s+(\d{4})$")
FINANCING_MATERIAL = "Facturation"


def _quarter_columns(header_row):
    """{col_index: (quarter_label, period_start)} depuis une ligne d'en-tête."""
    cols = {}
    for ci, val in enumerate(header_row):
        if isinstance(val, str):
            m = QUARTER_RE.match(val.strip())
            if m:
                q, year = int(m.group(1)), int(m.group(2))
                start = date(year, (q - 1) * 3 + 1, 1)
                cols[ci] = (f"T{q} {year}", start)
    return cols


def _num(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def import_eco_xlsx(file_stream):
    df = pd.read_excel(file_stream, sheet_name="Bilan", header=None)
    rows = [df.iloc[i].tolist() for i in range(len(df))]
    if not rows:
        return {"imported": 0, "updated": 0, "errors": ["Feuille Bilan vide."]}

    quarter_cols = _quarter_columns(rows[0])
    if not quarter_cols:
        return {"imported": 0, "updated": 0,
                "errors": ["Aucune colonne trimestre (T# AAAA) détectée."]}

    # (organism, material, quarter_label) -> {entrant, sortant, financing, period_start}
    acc = {}

    def _slot(org, mat, qlabel, pstart):
        return acc.setdefault(
            (org, mat, qlabel),
            {"entrant": 0.0, "sortant": 0.0, "financing": 0, "period_start": pstart},
        )

    # Labels qui ne sont pas des matières : ils ferment le bloc tonnages et
    # ouvrent (ou non) le bloc facturation.
    BLOCK_LABELS = {"volumes", "total", "bennes déchets", "bennes dechets"}

    cur_org = cur_mat = None
    mode = "tonnage"      # 'tonnage' puis 'totals' (volumes/facturation)
    facturation = False
    errors = []

    for r in rows[1:]:
        c0 = r[0] if len(r) > 0 else None
        c1 = r[1] if len(r) > 1 else None
        c2 = r[2] if len(r) > 2 else None

        if isinstance(c0, str) and c0.strip():
            cur_org = c0.strip().lower()

        label = c1.strip() if isinstance(c1, str) and c1.strip() else None
        if label:
            ll = label.lower()
            if ll == "facturation":
                mode, facturation = "totals", True
                # NB : organisme et label sur la même ligne → on continue le traitement.
            elif ll in BLOCK_LABELS:
                mode, facturation = "totals", False
                continue
            elif mode == "tonnage":
                cur_mat = label

        # Bloc facturation : c2 = organisme, valeurs = euros.
        if facturation and isinstance(c2, str) and c2.strip().lower() in ("ecologic", "ecomaison"):
            org = c2.strip().lower()
            for ci, (qlabel, pstart) in quarter_cols.items():
                val = _num(r[ci]) if ci < len(r) else None
                if val is None:
                    continue
                _slot(org, FINANCING_MATERIAL, qlabel, pstart)["financing"] += int(round(val * 100))
            continue

        # Bloc tonnages : c2 = Entrant / Sortant.
        if mode != "tonnage":
            continue
        direction = c2.strip().lower() if isinstance(c2, str) else ""
        if direction not in ("entrant", "sortant") or not cur_org or not cur_mat:
            continue
        for ci, (qlabel, pstart) in quarter_cols.items():
            val = _num(r[ci]) if ci < len(r) else None
            if val is None:
                continue
            _slot(cur_org, cur_mat, qlabel, pstart)[direction] = val

    imported = updated = 0
    for (org, mat, qlabel), d in acc.items():
        row = (
            EcoDeclaration.query
            .filter_by(organism=org, material=mat, quarter_label=qlabel)
            .first()
        )
        if row is None:
            row = EcoDeclaration(organism=org, material=mat, quarter_label=qlabel)
            db.session.add(row)
            imported += 1
        else:
            updated += 1
        row.period_start = d["period_start"]
        row.entrant_t = d["entrant"]
        row.sortant_t = d["sortant"]
        row.financing_cents = d["financing"]
        row.source = "import"
    db.session.commit()
    return {"imported": imported, "updated": updated, "errors": errors}
