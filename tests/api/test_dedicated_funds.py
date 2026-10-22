"""Phase A.6 : fonds dédiés (étape 3 de l'assistant) — dotation 689x / 19x en N, utilisation
19x / 789x les exercices suivants, plafonds, suppression, droits."""
from datetime import date

import pytest

from app.extensions import db
from app.models import Account, DedicatedFund, FiscalYear, Journal, JournalEntry
from app.services import closing


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def years(app):
    n = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    n1 = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    codes = ("6894", "194", "7894", "74", "706", "512")
    db.session.add_all([n, n1, Journal(code="BQ", label="Banque"),
                        *[Account(code=c, label=f"Compte {c}", account_type="OTHER") for c in codes]])
    db.session.commit()
    return n, n1


def _lines(entry):
    return {l.account.code: (l.debit_cents, l.credit_cents) for l in entry.lines}


def _fund(client, fy, **extra):
    body = {"label": "Subvention région projet jardin", "kind": "subsidy", "amount_cents": 10000,
            "resource_account_code": "74", **extra}
    return client.post(f"/api/v1/fiscal-years/{fy.id}/dedicated-funds", json=body)


def test_allocation_then_use(years, login_as):
    n, n1 = years
    client = login_as()
    assert _fund(client, n).status_code == 201
    fund = DedicatedFund.query.one()
    url = f"/api/v1/fiscal-years/{n.id}/dedicated-funds/{fund.id}/movements"
    assert client.post(url, json={"kind": "allocation", "amount_cents": 4000}).status_code == 201
    entry = JournalEntry.query.filter_by(source="DEDICATED_FUND").one()
    assert entry.entry_date == date(2025, 12, 31) and entry.journal.code == "OD" and entry.fiscal_year_id == n.id
    assert _lines(entry) == {"6894": (4000, 0), "194": (0, 4000)}
    assert closing.result(n)["expense_cents"] == 4000
    assert "60.00" in _error(client.post(url, json={"kind": "allocation", "amount_cents": 7000}), 422)["message"]
    _error(client.post(url, json={"kind": "use", "amount_cents": 1}), 422)  # rien à utiliser en N

    funds = client.get(f"/api/v1/fiscal-years/{n.id}/closing").get_json()["dedicated_funds"]["funds"]
    assert funds[0]["balance_start_cents"] == 0 and funds[0]["balance_end_cents"] == 4000
    assert funds[0]["allocatable_cents"] == 6000 and funds[0]["resource_account"] == "74"

    nxt = client.get(f"/api/v1/fiscal-years/{n1.id}/closing").get_json()["dedicated_funds"]["funds"]
    assert [f["balance_start_cents"] for f in nxt] == [4000]
    use_url = f"/api/v1/fiscal-years/{n1.id}/dedicated-funds/{fund.id}/movements"
    assert "40.00" in _error(client.post(use_url, json={"kind": "use", "amount_cents": 5000}), 422)["message"]
    assert client.post(use_url, json={"kind": "use", "amount_cents": 3000}).status_code == 201
    use = JournalEntry.query.filter_by(source="DEDICATED_FUND", fiscal_year_id=n1.id).one()
    assert _lines(use) == {"194": (3000, 0), "7894": (0, 3000)} and use.entry_date == date(2026, 12, 31)

    # La dotation de N ne se supprime plus une fois le fonds utilisé ensuite.
    allocation = fund.movements[0]
    assert "utilisé" in _error(client.delete(f"/api/v1/fiscal-years/{n.id}/dedicated-fund-movements/{allocation.id}"),
                               409)["message"]
    # Écritures gérées par l'assistant : pas de suppression depuis les écritures.
    _error(client.delete(f"/api/v1/entries/{use.id}"), 409)
    movement = fund.movements[1]
    assert client.delete(f"/api/v1/fiscal-years/{n1.id}/dedicated-fund-movements/{movement.id}").status_code == 200
    assert JournalEntry.query.filter_by(fiscal_year_id=n1.id).count() == 0
    _error(client.delete(f"/api/v1/fiscal-years/{n.id}/dedicated-funds/{fund.id}"), 409)  # dotation restante


def test_fund_validation_and_listing(years, login_as):
    n, n1 = years
    client = login_as()
    _error(_fund(client, n, label=""), 422)
    _error(_fund(client, n, kind="legs"), 422)
    _error(_fund(client, n, amount_cents=0), 422)
    assert "classe 7" in _error(_fund(client, n, resource_account_code="512"), 422)["message"]
    _fund(client, n)
    fund = DedicatedFund.query.one()
    # Fonds de N sans dotation : absent de N+1 (rien à reprendre).
    assert client.get(f"/api/v1/fiscal-years/{n1.id}/closing").get_json()["dedicated_funds"]["funds"] == []
    kinds = client.get(f"/api/v1/fiscal-years/{n.id}/closing").get_json()["dedicated_funds"]["kinds"]
    assert [k["value"] for k in kinds] == ["subsidy", "contribution", "public_generosity"]
    # Fonds créé en N+1 : inconnu de N.
    _error(client.post(f"/api/v1/fiscal-years/{n.id}/dedicated-funds/{fund.id + 99}/movements",
                       json={"kind": "allocation", "amount_cents": 1}), 404)
    assert client.delete(f"/api/v1/fiscal-years/{n.id}/dedicated-funds/{fund.id}").status_code == 200
    assert DedicatedFund.query.count() == 0


def test_missing_accounts_and_closed_year(years, login_as):
    n, _n1 = years
    client = login_as()
    _fund(client, n, kind="contribution")
    fund = DedicatedFund.query.one()
    url = f"/api/v1/fiscal-years/{n.id}/dedicated-funds/{fund.id}/movements"
    assert "6895" in _error(client.post(url, json={"kind": "allocation", "amount_cents": 100}), 422)["message"]
    n.status = "provisional"
    db.session.commit()
    _error(client.post(url, json={"kind": "allocation", "amount_cents": 100}), 409)
    _error(_fund(client, n), 409)


def test_accountant_reads_only(years, login_as):
    n, _n1 = years
    client = login_as(role="accountant")
    assert client.get(f"/api/v1/fiscal-years/{n.id}/closing").status_code == 200
    _error(_fund(client, n), 403)
