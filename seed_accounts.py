"""
Load a plan comptable from JSON into the database, plus the default journals.
Usage: python seed_accounts.py [asso|sci]

Idempotent: accounts already present are kept. Without an argument, the chart
is detected from the accounts already in the database (so an SCI database is
never filled with the associative chart); an empty database gets
$DEFAULT_INSTANCE_CHART, or "asso". An explicit chart that contradicts the one
already loaded is refused.
"""
import json
import os
import sys
from pathlib import Path

# Available charts of accounts: key -> JSON file under data/
CHARTS = {
    "asso": "plan_comptable_asso.json",
    "sci": "plan_comptable_sci.json",
    "societe": "plan_comptable_societe.json",
}
DEFAULT_CHART = "asso"
DATA_DIR = Path(__file__).parent / "data"


def load_chart(chart):
    return json.loads((DATA_DIR / CHARTS[chart]).read_text(encoding="utf-8"))


def detect_chart(existing_codes):
    """Chart whose own codes (absent from the other charts) are in the
    database, or None when the database has none of them (e.g. empty)."""
    codes = {chart: {a["code"] for a in load_chart(chart)} for chart in CHARTS}
    hits = {}
    for chart, own in codes.items():
        others = set().union(*(c for k, c in codes.items() if k != chart))
        hits[chart] = len((own - others) & set(existing_codes))
    best = max(hits, key=hits.get)
    return best if hits[best] else None


def resolve_chart(requested, existing_codes, default=None):
    """Chart to load. Raises SystemExit on an unknown or conflicting chart."""
    requested = (requested or "").strip().lower() or None
    default = (default or DEFAULT_CHART).strip().lower()
    for name in (requested, default):
        if name is not None and name not in CHARTS:
            raise SystemExit(
                f"Plan comptable inconnu : « {name} ». Choix : {', '.join(CHARTS)}."
            )
    detected = detect_chart(existing_codes)
    if requested and detected and requested != detected:
        raise SystemExit(
            f"La base contient déjà le plan « {detected} » : refus d'y ajouter "
            f"le plan « {requested} »."
        )
    return requested or detected or default


def main(argv):
    from app import create_app
    from app.extensions import db
    from app.models import Account, Journal

    app = create_app()
    with app.app_context():
        existing = {code for (code,) in db.session.query(Account.code)}
        chart = resolve_chart(argv[1] if len(argv) > 1 else None, existing,
                              os.environ.get("DEFAULT_INSTANCE_CHART"))

        created = 0
        for entry in load_chart(chart):
            if entry["code"] in existing:
                continue
            db.session.add(Account(
                code=entry["code"],
                label=entry["label"],
                account_type=entry["account_type"],
                is_header=entry["is_header"],
            ))
            created += 1

        # Wire parent relationships based on code prefix
        db.session.flush()
        all_accounts = {a.code: a for a in Account.query.all()}
        for account in all_accounts.values():
            if account.parent_id:
                continue
            # Find longest prefix that is a valid account code
            for length in range(len(account.code) - 1, 0, -1):
                parent_code = account.code[:length]
                if parent_code in all_accounts and parent_code != account.code:
                    account.parent_id = all_accounts[parent_code].id
                    break

        db.session.commit()
        print(f"Plan comptable « {chart} »: {created} comptes créés ({len(all_accounts)} au total).")

        # Seed default journals
        default_journals = [
            ("BQ", "Banque"),
            ("CA", "Caisse"),
            ("VT", "Ventes"),
            ("AC", "Achats"),
            ("OD", "Opérations diverses"),
            ("AN", "À-nouveaux"),
        ]
        j_created = 0
        for code, label in default_journals:
            if not Journal.query.filter_by(code=code).first():
                db.session.add(Journal(code=code, label=label))
                j_created += 1
        db.session.commit()
        print(f"Journaux: {j_created} journaux créés.")


if __name__ == "__main__":
    main(sys.argv)
