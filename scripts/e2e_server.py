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
                                  ("110000", "Report à nouveau", "EQUITY"), ("120000", "Excédent", "EQUITY"),
                                  ("530000", "Caisse", "ASSET"), ("581000", "Virements internes", "ASSET")):
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
        # Écriture non rapprochée réservée au parcours « projets » (ventilation d'une ligne de charge).
        conn.execute(text("INSERT INTO journal_entries (fiscal_year_id, journal_id, entry_date, reference, description, "
                          "is_balanced, source) VALUES (:f, :j, :d, 'BQ-E2E-PROJ', 'Matériel', 1, 'MANUAL')"),
                     {"f": fy, "j": bq, "d": f"{year}-04-20"})
        proj_entry = conn.execute(text("SELECT id FROM journal_entries WHERE reference = 'BQ-E2E-PROJ'")).scalar()
        for account, debit, credit in ((ids["606300"], 9000, 0), (ids["512000"], 0, 9000)):
            conn.execute(text("INSERT INTO journal_lines (entry_id, account_id, label, debit_cents, credit_cents) "
                              "VALUES (:e, :a, 'Matériel', :d, :c)"), {"e": proj_entry, "a": account, "d": debit, "c": credit})
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


# Image PNG 1 × 1 (signature des reçus de la base jetable).
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
                    "0000000d49444154789c63f80f00000101000518d84e0000000049454e44ae426082")


def _seed_donations(engine, slug):
    """Association prête à émettre des reçus : structure, signature, paramètres activés, un don de
    50,00 € d'une donatrice avec adresse (parcours « émettre et télécharger un reçu »)."""
    year = date.today().year
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO fiscal_years (label, start_date, end_date, closed, vat_liable) "
                          "VALUES (:l, :s, :e, 0, 0)"), {"l": str(year), "s": f"{year}-01-01", "e": f"{year}-12-31"})
        conn.execute(text("INSERT INTO journals (code, label) VALUES ('BQ', 'Banque')"))
        for code, label, kind in (("512000", "Banque", "ASSET"), ("7541", "Dons manuels", "REVENUE")):
            conn.execute(text("INSERT INTO accounts (code, label, account_type, is_header) VALUES (:c, :l, :t, 0)"),
                         {"c": code, "l": label, "t": kind})
        conn.execute(text(
            "INSERT INTO organization (name, rna, address_line1, postal_code, city, country, purpose, signatory_name, "
            "signatory_title, signature_path) VALUES ('Asso Dons E2E', 'W123456789', '1 rue des Lilas', '35000', "
            "'Rennes', 'France', 'Jardinage partagé', 'Camille Martin', 'Présidente', 'recus/signature.png')"))
        conn.execute(text(
            "INSERT INTO receipt_settings (enabled, eligibility, cgi_articles_json, donation_prefixes_json, default_mode, "
            "acknowledged_at) VALUES (1, 'general_interest', '[\"200\"]', '[\"7541\"]', 'annual', CURRENT_TIMESTAMP)"))
        conn.execute(text(
            "INSERT INTO entities (name, entity_type, is_member, is_benevole, person_kind, address_line1, postal_code, city) "
            "VALUES ('Donatrice E2E', 'AUTRE', 0, 0, 'individual', '3 rue des Dons', '75001', 'Paris')"))
        donor = conn.execute(text("SELECT id FROM entities WHERE name = 'Donatrice E2E'")).scalar()
        fy = conn.execute(text("SELECT id FROM fiscal_years")).scalar()
        bq = conn.execute(text("SELECT id FROM journals")).scalar()
        ids = {code: conn.execute(text("SELECT id FROM accounts WHERE code = :c"), {"c": code}).scalar()
               for code in ("512000", "7541")}
        conn.execute(text("INSERT INTO journal_entries (fiscal_year_id, journal_id, entry_date, reference, description, "
                          "is_balanced, source) VALUES (:f, :j, :d, 'BQ-DON-1', 'Don', 1, 'MANUAL')"),
                     {"f": fy, "j": bq, "d": f"{year}-01-15"})
        entry = conn.execute(text("SELECT id FROM journal_entries")).scalar()
        for account, debit, credit, entity in ((ids["512000"], 5000, 0, None), (ids["7541"], 0, 5000, donor)):
            conn.execute(text("INSERT INTO journal_lines (entry_id, account_id, label, debit_cents, credit_cents, entity_id) "
                              "VALUES (:e, :a, 'Don', :d, :c, :t)"),
                         {"e": entry, "a": account, "d": debit, "c": credit, "t": entity})
    folder = os.path.join(TMPDIR, "uploads", slug, "recus")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "signature.png"), "wb") as fh:
        fh.write(PNG)


def _seed_simple(engine):
    """Association en comptabilité simplifiée : exercice, comptes, un compte bancaire et une
    transaction importée non rapprochée (parcours « recette saisie, relevé catégorisé »)."""
    year = date.today().year
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO fiscal_years (label, start_date, end_date, closed, vat_liable) "
                          "VALUES (:l, :s, :e, 0, 0)"), {"l": str(year), "s": f"{year}-01-01", "e": f"{year}-12-31"})
        for code, label, kind in (("512000", "Banque", "ASSET"), ("756000", "Cotisations", "REVENUE"),
                                  ("606300", "Petit équipement", "EXPENSE")):
            conn.execute(text("INSERT INTO accounts (code, label, account_type, is_header) VALUES (:c, :l, :t, 0)"),
                         {"c": code, "l": label, "t": kind})
        bank = conn.execute(text("SELECT id FROM accounts WHERE code = '512000'")).scalar()
        conn.execute(text("INSERT INTO bank_accounts (label, account_id, kind) VALUES ('Banque simple', :a, 'bank')"),
                     {"a": bank})
        ba = conn.execute(text("SELECT id FROM bank_accounts")).scalar()
        conn.execute(text("INSERT INTO bank_transactions (bank_account_id, fitid, transaction_date, amount_cents, label, "
                          "reconciled, source, is_reversed) VALUES (:b, 'S-1', :d, -2500, 'CB PAPETERIE', 0, 'ofx', 0)"),
                     {"b": ba, "d": f"{year}-02-10"})


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
            if spec.get("donations"):
                _seed_donations(engine, spec["slug"])
            if spec.get("simple"):
                _seed_simple(engine)
            engine.dispose()
            db.session.add(Instance(slug=spec["slug"], label=spec["label"], chart=spec["chart"],
                                    bookkeeping=spec.get("bookkeeping", "double"), database_url=url))
        db.session.commit()


def main():
    app = create_app("development")
    app.instance_path = TMPDIR
    seed(app)
    print(f"[e2e] base jetable : {TMPDIR}", flush=True)
    app.run(host="127.0.0.1", port=FIXTURES["port"], debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
