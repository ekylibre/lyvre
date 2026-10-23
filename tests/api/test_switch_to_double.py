"""Lot D.5 : passage de la comptabilité simplifiée à la partie double (sans reprise), retour refusé
dès qu'une écriture ne se lit pas en recettes / dépenses, première clôture en double avec des
à-nouveaux calculés en cumulé (résultats antérieurs en report à nouveau)."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, FiscalYear, Instance, Journal
from app.services import closing
from app.services.ledger import post_entry


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def books(app):
    y25 = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    y26 = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    accounts = {c: Account(code=c, label=f"Compte {c}", account_type="OTHER")
                for c in ("512", "530", "756", "6061", "110", "119", "120", "129", "401")}
    db.session.add_all([y25, y26, Journal(code="BQ", label="Banque"), *accounts.values()])
    db.session.commit()
    ids = {c: a.id for c, a in accounts.items()}
    bq = Journal.query.one().id

    def op(year, day, debit, credit, cents):
        post_entry(year.id, bq, day, "Op", [{"account_id": ids[debit], "debit_cents": cents},
                                            {"account_id": ids[credit], "credit_cents": cents}], source="SIMPLE")
    op(y25, date(2025, 3, 1), "512", "756", 10000)   # 2025 : +100 de cotisations
    op(y25, date(2025, 4, 1), "6061", "512", 3000)   #        −30 d'achats → résultat 2025 : 70
    op(y26, date(2026, 2, 1), "512", "756", 5000)    # 2026 : +50
    op(y26, date(2026, 3, 1), "530", "756", 1000)    #        +10 en caisse
    op(y26, date(2026, 5, 1), "6061", "512", 2500)   #        −25 → résultat 2026 : 35
    return {"y25": y25, "y26": y26, **ids}


def test_switch_modes(books, login_as):
    client = login_as(is_admin=True, role="admin")
    inst = Instance.query.one()
    url = f"/api/v1/instances/{inst.id}"
    assert client.patch(url, json={"label": inst.label, "bookkeeping": "simple"}).get_json()["item"]["bookkeeping"] == "simple"
    assert client.patch(url, json={"label": inst.label, "bookkeeping": "double"}).get_json()["item"]["bookkeeping"] == "double"
    # Une écriture de tiers (401) : retour au simple refusé.
    post_entry(books["y26"].id, Journal.query.one().id, date(2026, 6, 1), "Facture", [
        {"account_id": books["6061"], "debit_cents": 100}, {"account_id": books["401"], "credit_cents": 100}])
    assert "1 écriture(s)" in _error(client.patch(url, json={"label": inst.label, "bookkeeping": "simple"}), 409)["message"]
    _error(client.patch(url, json={"label": inst.label, "bookkeeping": "autre"}), 422)


def test_switch_needs_global_admin(books, login_as):
    client = login_as(role="admin")  # administrateur de l'instance, pas global
    _error(client.patch(f"/api/v1/instances/{Instance.query.one().id}", json={"bookkeeping": "double"}), 403)


def test_first_double_close_uses_cumulative_balances(books):
    y26 = books["y26"]
    assert closing.cumulative_opening(y26) and not closing.cumulative_opening(books["y25"])
    lines = {l["account_code"]: (l["debit_cents"], l["credit_cents"]) for l in closing.opening_lines(y26)}
    assert lines == {
        "512": (10000 - 3000 + 5000 - 2500, 0),   # solde cumulé depuis 2025
        "530": (1000, 0),
        "110": (0, 7000),                          # résultat 2025, jamais repris : report à nouveau
        "120": (0, 3500),                          # résultat 2026
    }
    assert sum(d for d, _ in lines.values()) == sum(c for _, c in lines.values())
