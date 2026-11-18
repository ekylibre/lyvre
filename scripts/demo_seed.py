"""Données de la démonstration en ligne (demo.lyvre.org, `LYVRE_DEMO=1`, lot L7 du site).

Tout est fabriqué (noms, adresses, e-mails en @example.org, SIREN de test). Lancé par `docker/entrypoint.sh` après
les migrations et `seed_meta.py`, dans un dossier d'instance vidé au démarrage (`DEMO_RESET_ON_START`) :

- « Les Jardins Partagés » (association) : instance par défaut de `seed_meta.py` (DEFAULT_INSTANCE_*), structure,
  adhérents et adhésions HelloAsso (`scripts/e2e_demo.py`), compte bancaire, écritures et relevé à rapprocher ;
- « SCI des Tilleuls » (SCI) : factures, devis, bail avec quittance et dépôt de garantie, abonnements ;
- « Atelier Bois & Cie » (société) : factures et encaissements ;
- « EARL des Pins (fictive) » : exploitation du jeu d'essai agricole (tests/fixtures/agri).

Les bases sont créées comme dans l'application (migrations Alembic, plan comptable, règles) et remplies par
l'API, avec un client de test Flask connecté au compte de démonstration. Ce compte n'est pas administrateur
global : il est administrateur de chaque instance de démonstration. L'administrateur de `seed_meta.py` est
désactivé. Sans effet si le compte de démonstration existe déjà (redémarrage sans remise à zéro).
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sqlalchemy import text  # noqa: E402

from app import create_app, demo  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Instance, InstanceMembership, User  # noqa: E402
from app.services.instance_provisioning import build_sqlite_url, provision_sqlite_database  # noqa: E402
from app.tenant import get_tenant_engine  # noqa: E402

INSTANCES = [
    # slug, libellé, plan, intégrations activées
    ("tilleuls", "SCI des Tilleuls", "sci", []),
    ("atelier-bois", "Atelier Bois & Cie", "societe", []),
    ("earl-des-pins", "EARL des Pins (fictive)", "agri", []),
]
AGRI_FIXTURE = "A_earl_porcs_rs"


class Api:
    """Client de l'API JSON (`/api/v1`) avec la session et le jeton CSRF, comme la SPA."""

    def __init__(self, app):
        self.client = app.test_client()
        self.csrf = ""

    def _token(self):
        if not self.csrf:  # comme la SPA : balise meta de la page, puis jeton de la session une fois connecté
            page = self.client.get("/login").get_data(as_text=True)
            self.csrf = re.search(r'name="csrf-token" content="([^"]+)"', page).group(1)
        return self.csrf

    def call(self, method, path, body=None):
        resp = self.client.open(f"/api/v1{path}", method=method, json=body,
                                headers={"X-CSRFToken": self._token()} if method != "GET" else {})
        data = resp.get_json(silent=True) or {}
        if resp.status_code >= 400:
            raise RuntimeError(f"{method} {path} → {resp.status_code} {json.dumps(data, ensure_ascii=False)[:400]}")
        return data

    def login(self, email, password):
        self.csrf = self.call("POST", "/session/login", {"email": email, "password": password})["csrf_token"]

    def use(self, instance):
        self.csrf = self.call("POST", "/session/instance", {"instance_id": instance.id})["csrf_token"]


# ------------------------------------------------------------------ outils


def account(api, prefix):
    """Premier compte de détail dont le code commence par `prefix` (plan comptable de l'instance)."""
    for item in api.call("GET", f"/accounts?q={prefix}&limit=50")["results"]:
        if item["code"].startswith(prefix):
            return item
    raise RuntimeError(f"Compte {prefix} introuvable.")


def journal(api, code, label):
    for item in api.call("GET", "/journals").get("items", []):
        if item["code"] == code:
            return item
    return api.call("POST", "/journals", {"code": code, "label": label})["item"]


def fiscal_year(api, year):
    for item in api.call("GET", "/fiscal-years")["items"]:
        if item["start_date"] == f"{year}-01-01":
            return item
    return api.call("POST", "/fiscal-years", {"label": str(year), "start_date": f"{year}-01-01",
                                              "end_date": f"{year}-12-31"})["item"]


def bank_account(api, label, code="512"):
    items = api.call("GET", "/bank-accounts")["items"]
    if items:
        return items[0]
    return api.call("POST", "/bank-accounts", {"label": label, "account_id": account(api, code)["id"],
                                               "kind": "bank"})["item"]


def entry(api, fy, jr, day, description, lines):
    """Écriture équilibrée : `lines` = [(compte, débit en euros, crédit en euros)]."""
    api.call("POST", "/entries", {
        "fiscal_year_id": fy["id"], "journal_id": jr["id"], "entry_date": day.isoformat(), "description": description,
        "lines": [{"account_id": acc["id"], "label": description, "debit_cents": round(debit * 100),
                   "credit_cents": round(credit * 100)} for acc, debit, credit in lines]})


def bank_lines(inst, ba_id, rows):
    """Relevé importé non rapproché (pas d'API d'écriture directe : un relevé vient d'un fichier ou de Qonto)."""
    with get_tenant_engine(inst).begin() as conn:
        for fitid, day, amount, label in rows:
            conn.execute(text("INSERT INTO bank_transactions (bank_account_id, fitid, transaction_date, amount_cents, "
                              "label, reconciled, source, is_reversed) VALUES (:b, :f, :d, :a, :l, 0, 'ofx', 0)"),
                         {"b": ba_id, "f": fitid, "d": day.isoformat(), "a": round(amount * 100), "l": label})


def months_ago(today, n, day=1):
    month = today.month - n
    year = today.year + (month - 1) // 12
    return date(year, (month - 1) % 12 + 1, day)


# ------------------------------------------------------------------ jeux de données


def seed_association(api, inst, today):
    from scripts import e2e_demo
    e2e_demo.seed(get_tenant_engine(inst), "", brevo=False)  # structure, exercice, 12 adhérents (HelloAsso)
    fy = fiscal_year(api, today.year)
    bq = journal(api, "BQ", "Banque")
    ba = bank_account(api, "Crédit Coopératif")
    bank = ba["account"]
    start = date(today.year, 1, 1)
    for offset, description, prefix, amount in (
        (20, "Cotisations janvier (HelloAsso)", "756", 240), (35, "Subvention de la commune", "74", 1500),
        (48, "Graines et plants", "60", 186.4), (60, "Assurance multirisque", "616", 312),
        (75, "Location du local", "613", 450), (90, "Cotisations printemps (HelloAsso)", "756", 180),
        (110, "Outils de jardinage", "60", 94.9), (130, "Vente de légumes au marché", "70", 265),
    ):
        day = start + timedelta(days=offset)
        if day > today:
            break
        acc = account(api, prefix)
        income = prefix.startswith("7")
        entry(api, fy, bq, day, description, [(bank, amount, 0), (acc, 0, amount)] if income
              else [(acc, amount, 0), (bank, 0, amount)])
    recent = max(start, today - timedelta(days=20))
    bank_lines(inst, ba["id"], [("JP-1", recent, -48.6, "CB JARDINERIE DU CENTRE"),
                                ("JP-2", recent + timedelta(days=3), 60, "VIR ADHESION FAMILLE MOREAU"),
                                ("JP-3", recent + timedelta(days=6), -25, "PRLV ASSURANCE MUTUELLE")])


def seed_sales(api, inst, today, *, name, legal_form, client_name, with_lease):
    """Structure, client, factures émises (une encaissée par virement, une par chèque), devis accepté, brouillon ;
    pour une SCI, bail avec avis, quittance et dépôt de garantie, abonnements."""
    fy = fiscal_year(api, today.year)
    journal(api, "BQ", "Banque")
    api.call("PUT", "/organization", {"name": name, "legal_form": legal_form, "siren": "123456782",
                                      "address_line1": "8 allée des Tilleuls", "postal_code": "17100", "city": "Saintes",
                                      "country": "France", "signatory_name": "Claire Fontaine", "share_capital": "10000",
                                      "rcs_city": "Saintes"})
    api.call("PUT", "/billing-settings", {"iban": "FR76 3000 6000 0112 3456 7890 189"})
    client = api.call("POST", "/tiers", {"name": client_name, "entity_type": "CLIENT", "person_kind": "company",
                                         "address_line1": "2 avenue des Platanes", "postal_code": "69001",
                                         "city": "Lyon", "email": "contact@example.org"})["item"]["id"]
    supplier = api.call("POST", "/tiers", {"name": "Opérateur Télécom", "entity_type": "FOURNISSEUR"})["item"]["id"]
    ba = bank_account(api, "Banque Populaire")
    bank_lines(inst, ba["id"], [("VE-1", today, 1200, f"VIR {client_name.upper()}")])
    invoices = [
        [("Gestion locative — trimestre", "1", "450"), ("Frais de dossier", "1", "120")],
        [("Audit énergétique", "2", "380")],
        [("Mise à disposition de la salle", "3", "150"), ("Ménage", "3", "40")],
        [("Conseil en gestion", "1", "1200")],
    ]
    ids = []
    for rows in invoices:
        item = api.call("POST", "/sales", {"entity_id": client, "issue_date": today.isoformat(), "lines": [
            {"label": label, "quantity": q, "unit_price": p, "vat_rate": "0", "account_code": "706"}
            for label, q, p in rows]})["item"]
        api.call("POST", f"/sales/{item['id']}/issue")
        ids.append(item["id"])
    options = api.call("GET", f"/sales/{ids[3]}/payment-options")
    if options.get("candidates"):
        api.call("POST", "/sales/match", {"bank_transaction_id": options["candidates"][0]["id"],
                                          "allocations": [{"sale_id": ids[3], "amount_cents": 120000}]})
    bank_id = options["accounts"][0]["value"]
    api.call("POST", f"/sales/{ids[1]}/payments", {"amount": "300", "paid_on": today.isoformat(),
                                                    "bank_account_id": bank_id, "method": "check"})
    quote = api.call("POST", "/sales", {"kind": "quote", "entity_id": client, "issue_date": today.isoformat(), "lines": [
        {"label": "Rénovation de la cage d'escalier", "quantity": "1", "unit_price": "6800", "vat_rate": "0"}]})["item"]
    api.call("POST", f"/sales/{quote['id']}/issue")
    api.call("POST", f"/sales/{quote['id']}/quote-status", {"status": "accepted"})
    api.call("POST", "/sales", {"entity_id": client, "issue_date": today.isoformat(),
                                "lines": [{"label": "Location du parking", "unit_price": "90", "vat_rate": "0"}]})
    if not with_lease:
        return fy
    first = date(today.year, today.month, 1)
    lease = api.call("POST", "/leases", {"entity_id": client, "unit_label": "Appartement 2B",
                                         "address_line1": "10 rue des Lilas", "postal_code": "17100", "city": "Saintes",
                                         "start_date": first.isoformat(), "rent": "850", "charges": "60",
                                         "deposit": "1700", "due_day": 1})["item"]
    due = api.call("GET", "/sales/due")["items"]
    if due:
        api.call("POST", "/sales/issue-batch", {"ids": [s["id"] for s in due]})
    invoices = api.call("GET", f"/leases/{lease['id']}")["item"].get("invoices") or []
    if invoices:
        api.call("POST", f"/sales/{invoices[0]['id']}/payments", {"amount": "910", "bank_account_id": bank_id,
                                                                  "method": "transfer"})
        api.call("POST", f"/sales/{invoices[0]['id']}/rent-receipt")
    api.call("POST", f"/leases/{lease['id']}/deposit", {"paid_on": today.isoformat(), "bank_account_id": bank_id})
    start = months_ago(today, 4)
    for label, category, amount, frequency, renewal in (
        ("Box internet et téléphonie", "internet", "45", "monthly", None),
        ("Assurance propriétaire non occupant", "insurance", "620", "yearly", 40),
        ("Logiciel de gestion", "software", "29", "monthly", None),
    ):
        body = {"label": label, "entity_id": supplier, "category": category, "amount": amount, "frequency": frequency,
                "due_day": 5, "start_date": start.isoformat()}
        if renewal:
            body |= {"renewal_date": (today + timedelta(days=renewal)).isoformat(), "notice_days": 30}
        api.call("POST", "/subscriptions", body)
    return fy


def seed_agri(app, inst):
    """Exploitation du jeu d'essai, chargée par les services de Lyvre dans le contexte de son instance."""
    from flask import g

    from scripts.agri_fixtures.load import FIXTURES, load

    with app.test_request_context():
        g.current_instance, g.tenant_engine = inst, get_tenant_engine(inst)
        load(FIXTURES / AGRI_FIXTURE)


# ------------------------------------------------------------------ instances et compte


def create_instance(slug, label, chart, integrations):
    url = build_sqlite_url(slug)
    provision_sqlite_database(url, chart=chart)
    inst = Instance(slug=slug, label=label, database_url=url, chart=chart, bookkeeping="double",
                    has_associates=chart in ("sci", "societe"), is_active=True,
                    integrations=json.dumps({"enabled": integrations, "dismissed": []}))
    db.session.add(inst)
    db.session.flush()
    return inst


def main() -> int:
    app = create_app()
    creds = demo.credentials()
    today = date.today()
    with app.app_context():
        if db.session.query(User).filter(User.email == creds["email"]).first():
            print("[demo] Compte de démonstration déjà présent : rien à faire.")
            return 0
        for user in db.session.query(User):  # administrateur de seed_meta.py : inutile et jamais exposé
            user.is_active = False
        user = User(email=creds["email"], full_name="Visiteur de la démo", is_admin=False, is_active=True)
        user.set_password(creds["password"])
        db.session.add(user)
        default = db.session.query(Instance).order_by(Instance.id).first()
        default.integrations = json.dumps({"enabled": [], "dismissed": []})
        instances = [default] + [create_instance(*spec) for spec in INSTANCES]
        for inst in instances:
            db.session.add(InstanceMembership(user=user, instance=inst, role="admin"))
        db.session.commit()
        ids = {inst.slug: inst.id for inst in instances}
        default_slug = default.slug

    def fresh(slug):
        return db.session.get(Instance, ids[slug])

    api = Api(app)
    api.login(creds["email"], creds["password"])
    with app.app_context():
        steps = [
            (default_slug, lambda inst: seed_association(api, inst, today)),
            ("tilleuls", lambda inst: seed_sales(api, inst, today, name="SCI des Tilleuls",
                                                 legal_form="Société civile immobilière",
                                                 client_name="Agence Horizon", with_lease=True)),
            ("atelier-bois", lambda inst: seed_sales(api, inst, today, name="Atelier Bois & Cie",
                                                     legal_form="SAS", client_name="Maison Durable",
                                                     with_lease=False)),
            ("earl-des-pins", lambda inst: seed_agri(app, inst)),
        ]
        failed = 0
        for slug, step in steps:
            inst = fresh(slug)
            try:
                api.use(inst)
                step(inst)
                print(f"[demo] {inst.label} : prêt.")
            except Exception as exc:  # noqa: BLE001 — une structure incomplète n'empêche pas les autres
                failed += 1
                print(f"[demo] {inst.label} : incomplet — {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
