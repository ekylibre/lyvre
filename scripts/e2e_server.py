"""Serveur Flask des tests de bout en bout (Playwright, frontend/e2e/).

Bases SQLite et dossier d'instance jetables (jamais les vraies données) :
méta-base avec l'utilisateur et les instances de frontend/e2e/fixtures.json,
une base tenant vide par instance. Les fichiers du front doivent être construits
(`npm --prefix frontend run build`).
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

with open(os.path.join(ROOT, "frontend", "e2e", "fixtures.json"), encoding="utf-8") as fh:
    FIXTURES = json.load(fh)

TMPDIR = tempfile.mkdtemp(prefix="compta-asso-e2e-")
os.environ["META_DATABASE_URL"] = f"sqlite:///{os.path.join(TMPDIR, 'meta.db')}"
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(TMPDIR, 'default.db')}"
os.environ.pop("VITE_DEV_SERVER", None)

from datetime import date  # noqa: E402

from sqlalchemy import create_engine, text  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Instance, User  # noqa: E402


def _seed_books(engine):
    """Exercice de l'année, journaux et quelques comptes (parcours de saisie)."""
    year = date.today().year
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO fiscal_years (label, start_date, end_date, closed, vat_liable) "
                          "VALUES (:l, :s, :e, 0, 0)"),
                     {"l": str(year), "s": f"{year}-01-01", "e": f"{year}-12-31"})
        for code, label in (("AC", "Achats"), ("BQ", "Banque"), ("OD", "Opérations diverses")):
            conn.execute(text("INSERT INTO journals (code, label) VALUES (:c, :l)"), {"c": code, "l": label})
        for code, label, kind in (("512000", "Banque", "ASSET"), ("606300", "Petit équipement", "EXPENSE"),
                                  ("401000", "Fournisseurs", "TIERS"), ("706000", "Prestations", "REVENUE"),
                                  ("110000", "Report à nouveau", "EQUITY"), ("120000", "Excédent", "EQUITY")):
            conn.execute(text("INSERT INTO accounts (code, label, account_type, is_header) VALUES (:c, :l, :t, 0)"),
                         {"c": code, "l": label, "t": kind})
        # Rapprochement : un compte bancaire, un débit qui a son écriture, un crédit sans écriture.
        ids = {code: conn.execute(text("SELECT id FROM accounts WHERE code = :c"), {"c": code}).scalar()
               for code in ("512000", "606300")}
        conn.execute(text("INSERT INTO bank_accounts (label, account_id) VALUES ('Banque E2E', :a)"),
                     {"a": ids["512000"]})
        ba = conn.execute(text("SELECT id FROM bank_accounts")).scalar()
        for fitid, day, amount, label in (("E2E-1", 10, -4500, "CB LEROY MERLIN"), ("E2E-2", 12, 15000, "VIR CLIENT DUPONT")):
            conn.execute(text("INSERT INTO bank_transactions (bank_account_id, fitid, transaction_date, amount_cents, "
                              "label, reconciled, source, is_reversed) VALUES (:b, :f, :d, :a, :l, 0, 'ofx', 0)"),
                         {"b": ba, "f": fitid, "d": f"{year}-03-{day:02d}", "a": amount, "l": label})
        fy = conn.execute(text("SELECT id FROM fiscal_years")).scalar()
        bq = conn.execute(text("SELECT id FROM journals WHERE code = 'BQ'")).scalar()
        conn.execute(text("INSERT INTO journal_entries (fiscal_year_id, journal_id, entry_date, reference, description, "
                          "is_balanced, source) VALUES (:f, :j, :d, 'BQ-E2E-1', 'Perceuse', 1, 'MANUAL')"),
                     {"f": fy, "j": bq, "d": f"{year}-03-10"})
        entry = conn.execute(text("SELECT id FROM journal_entries WHERE reference = 'BQ-E2E-1'")).scalar()
        for account, debit, credit in ((ids["606300"], 4500, 0), (ids["512000"], 0, 4500)):
            conn.execute(text("INSERT INTO journal_lines (entry_id, account_id, label, debit_cents, credit_cents) "
                              "VALUES (:e, :a, 'Perceuse', :d, :c)"), {"e": entry, "a": account, "d": debit, "c": credit})
        # Exercice ancien (6 ans) avec une écriture : assistant de clôture complet et FEC sans toucher
        # à l'exercice courant des autres parcours.
        old = year - 6
        conn.execute(text("INSERT INTO fiscal_years (label, start_date, end_date, closed, vat_liable) "
                          "VALUES (:l, :s, :e, 0, 0)"), {"l": str(old), "s": f"{old}-01-01", "e": f"{old}-12-31"})
        # Exercice suivant (vide) : reçoit les à-nouveaux et l'affectation de l'assistant.
        conn.execute(text("INSERT INTO fiscal_years (label, start_date, end_date, closed, vat_liable) "
                          "VALUES (:l, :s, :e, 0, 0)"), {"l": str(old + 1), "s": f"{old + 1}-01-01", "e": f"{old + 1}-12-31"})
        old_fy = conn.execute(text("SELECT id FROM fiscal_years WHERE label = :l"), {"l": str(old)}).scalar()
        conn.execute(text("INSERT INTO journal_entries (fiscal_year_id, journal_id, entry_date, reference, description, "
                          "is_balanced, source) VALUES (:f, :j, :d, 'BQ-E2E-OLD', 'Prestation', 1, 'MANUAL')"),
                     {"f": old_fy, "j": bq, "d": f"{old}-06-15"})
        old_entry = conn.execute(text("SELECT id FROM journal_entries WHERE reference = 'BQ-E2E-OLD'")).scalar()
        income = conn.execute(text("SELECT id FROM accounts WHERE code = '706000'")).scalar()
        for account, debit, credit in ((ids["512000"], 25000, 0), (income, 0, 25000)):
            conn.execute(text("INSERT INTO journal_lines (entry_id, account_id, label, debit_cents, credit_cents) "
                              "VALUES (:e, :a, 'Prestation', :d, :c)"), {"e": old_entry, "a": account, "d": debit, "c": credit})


def seed(app):
    with app.app_context():
        db.create_all()
        user = User(email=FIXTURES["user"]["email"], full_name="Testeur E2E", is_admin=True)
        user.set_password(FIXTURES["user"]["password"])
        db.session.add(user)
        for spec in FIXTURES["instances"]:
            url = f"sqlite:///{os.path.join(TMPDIR, spec['slug'] + '.db')}"
            engine = create_engine(url)
            db.metadata.create_all(engine)  # tables tenant (la méta-base a ses propres métadonnées)
            if spec.get("books"):
                _seed_books(engine)
            engine.dispose()
            db.session.add(Instance(slug=spec["slug"], label=spec["label"], chart=spec["chart"],
                                    database_url=url))
        db.session.commit()


def main():
    app = create_app("development")
    app.instance_path = TMPDIR
    seed(app)
    print(f"[e2e] base jetable : {TMPDIR}", flush=True)
    app.run(host="127.0.0.1", port=FIXTURES["port"], debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
