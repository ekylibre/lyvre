"""Relevés de compte (lot RQ1) : mois visés, récupération Qonto (nouveau, inchangé sans téléchargement,
remplacé, lien expiré renouvelé, fichier non PDF), liste, PDF, droits, compte non supprimable."""
from datetime import date

import pytest
import requests

from app.extensions import db
from app.models import Account, BankAccount, BankStatement, FiscalYear
from app.services import bank_statements, external_config, qonto_client
from app.services.qonto_client import QontoError

TODAY = date(2026, 11, 1)
PDF_V1 = b"%PDF-1.7 releve juillet v1"
PDF_V2 = b"%PDF-1.7 releve juillet v2 corrige"


def _item(period, size, sid=None, url=None):
    return {"id": sid or f"st-{period}", "bank_account_id": "qa-1", "period": period,
            "file": {"file_name": f"2026-{period[:2]}-statement.pdf", "file_content_type": "application/pdf",
                     "file_size": size, "file_url": url or f"https://s3.example/{period}"}}


class FakeQonto:
    def __init__(self):
        self.items = [_item("10-2026", len(PDF_V1)), _item("09-2026", len(PDF_V1)), _item("07-2026", len(PDF_V1))]
        self.files = {f"https://s3.example/{p}": PDF_V1 for p in ("10-2026", "09-2026", "08-2026", "07-2026")}
        self.expired, self.calls = set(), []

    def list_statements(self, account_id, period_from, period_to):
        self.calls.append(("list", account_id, period_from, period_to))
        return self.items

    def statement(self, statement_id):
        self.calls.append(("statement", statement_id))
        period = statement_id.removeprefix("st-")
        return _item(period, len(PDF_V1), url=f"https://s3.example/fresh/{period}")

    def download(self, url):
        self.calls.append(("download", url))
        if url in self.expired:
            response = requests.Response()
            response.status_code = 403
            raise QontoError("expiré", response=response)
        return self.files.get(url) or self.files.get(url.replace("/fresh", ""))


def _bank(app, login_as, monkeypatch, tmp_path, role="treasurer"):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))  # PDF écrits hors du dossier instance/
    client = login_as(role=role)
    account = Account(code="512", label="Banque", account_type="TRESORERIE")
    db.session.add_all([account, FiscalYear(label="2026-2027", start_date=date(2026, 7, 1), end_date=date(2027, 6, 30))])
    db.session.flush()
    ba = BankAccount(label="Qonto — Compte principal", account_id=account.id, qonto_account_id="qa-1")
    db.session.add(ba)
    db.session.commit()
    fake = FakeQonto()
    external_config.set_many("qonto", {"login": "ekylibre-1234", "secret_key": "secret"})
    monkeypatch.setattr(qonto_client, "from_app_config", lambda *a, **k: fake)
    monkeypatch.setattr(bank_statements, "months", lambda fy, today=None, _m=bank_statements.months: _m(fy, TODAY))
    return {"client": client, "ba": ba, "fake": fake}


@pytest.fixture()
def bank(app, login_as, monkeypatch, tmp_path):
    return _bank(app, login_as, monkeypatch, tmp_path)


def test_months_of_the_current_fiscal_year():
    fy = FiscalYear(start_date=date(2026, 7, 1), end_date=date(2027, 6, 30))
    assert bank_statements.months(fy, date(2026, 11, 1)) == [date(2026, m, 1) for m in (7, 8, 9, 10)]
    assert bank_statements.months(fy, date(2026, 7, 15)) == []  # juillet n'est pas terminé
    assert len(bank_statements.months(fy, date(2028, 1, 1))) == 12
    assert bank_statements.months(None) == []


def test_fetch_stores_then_skips_unchanged_and_replaces_changed(bank):
    ba, fake = bank["ba"], bank["fake"]
    result = bank_statements.fetch_qonto(ba)
    assert result == {"new": 3, "replaced": 0, "unchanged": 0, "errors": []}
    assert fake.calls[0] == ("list", "qa-1", "07-2026", "10-2026")
    july = BankStatement.query.filter_by(period=date(2026, 7, 1)).one()
    assert july.file_path == f"releves/{ba.id}/2026-07.pdf" and july.qonto_id == "st-07-2026"
    assert bank_statements.path_for(july).read_bytes() == PDF_V1
    fake.calls.clear()
    assert bank_statements.fetch_qonto(ba)["unchanged"] == 3
    assert [c for c in fake.calls if c[0] == "download"] == []  # même identifiant et même taille : rien téléchargé
    # Qonto régénère le relevé de juillet : remplacé.
    fake.items[2] = _item("07-2026", len(PDF_V2))
    fake.files["https://s3.example/07-2026"] = PDF_V2
    result = bank_statements.fetch_qonto(ba)
    assert result["replaced"] == 1 and result["unchanged"] == 2
    db.session.refresh(july)
    assert july.replaced_at is not None and bank_statements.path_for(july).read_bytes() == PDF_V2


def test_expired_link_is_renewed_and_bad_file_is_reported(bank):
    ba, fake = bank["ba"], bank["fake"]
    fake.expired.add("https://s3.example/10-2026")
    fake.files["https://s3.example/09-2026"] = b"<html>pas un pdf</html>"
    result = bank_statements.fetch_qonto(ba)
    assert result["new"] == 2 and ("statement", "st-10-2026") in fake.calls
    assert result["errors"] == ["Relevé 09/2026 : le fichier reçu n'est pas un PDF."]
    assert BankStatement.query.filter_by(period=date(2026, 9, 1)).count() == 0


def test_api_list_fetch_pdf_and_delete_guard(bank):
    client, ba = bank["client"], bank["ba"]
    body = client.post(f"/api/v1/bank-accounts/{ba.id}/statements/fetch").get_json()
    assert body["result"]["new"] == 3 and "3 relevé(s) récupéré(s)" in body["notices"][0]["message"]
    items = client.get(f"/api/v1/bank-accounts/{ba.id}/statements").get_json()["items"]
    assert [i["period"] for i in items] == ["2026-10", "2026-09", "2026-08", "2026-07"]
    assert items[2]["statement"] is None  # août manquant
    pdf = client.get(items[0]["statement"]["url"])
    assert pdf.status_code == 200 and pdf.mimetype == "application/pdf" and pdf.data == PDF_V1
    assert "inline" in pdf.headers["Content-Disposition"]
    assert client.delete(f"/api/v1/bank-accounts/{ba.id}").status_code == 409  # relevés conservés


def test_accountant_reads_but_does_not_fetch(app, login_as, monkeypatch, tmp_path):
    bank = _bank(app, login_as, monkeypatch, tmp_path, role="accountant")
    bank_statements.fetch_qonto(bank["ba"])
    accountant = bank["client"]
    ba_id = bank["ba"].id
    items = accountant.get(f"/api/v1/bank-accounts/{ba_id}/statements").get_json()["items"]
    assert accountant.get(items[0]["statement"]["url"]).status_code == 200
    assert accountant.post(f"/api/v1/bank-accounts/{ba_id}/statements/fetch").status_code == 403


def test_fetch_requires_a_qonto_account_and_integration(bank):
    client, ba = bank["client"], bank["ba"]
    other = BankAccount(label="Crédit Agricole", account_id=ba.account_id)
    db.session.add(other)
    db.session.commit()
    assert client.post(f"/api/v1/bank-accounts/{other.id}/statements/fetch").status_code == 409
    assert client.get(f"/api/v1/bank-accounts/{other.id}/statements").get_json()["qonto"] is None
    external_config.set_enabled("qonto", False)
    resp = client.post(f"/api/v1/bank-accounts/{ba.id}/statements/fetch")
    assert resp.status_code == 409 and resp.get_json()["error"]["code"] == "integration_required"


# ------------------------------------------------------------------ lot RQ2 : en fin de synchronisation Qonto

class SyncingQonto(FakeQonto):
    def list_transactions(self, account_id, *, statuses, page=1, per_page=100, **window):
        return [], {"current_page": 1, "next_page": None, "total_count": 0}


def test_sync_fetches_new_statements(bank):
    from app.services import qonto_sync
    fake = SyncingQonto()
    result = qonto_sync.sync_bank_account(bank["ba"].id, client=fake)
    assert result["statements"] == 3 and result["errors"] == []
    assert BankStatement.query.count() == 3
    assert qonto_sync.sync_bank_account(bank["ba"].id, client=fake)["statements"] == 0  # rien de nouveau


def test_statement_failure_does_not_fail_the_sync(bank):
    from app.services import qonto_sync

    class Refusing(SyncingQonto):
        def list_statements(self, *args):
            response = requests.Response()
            response.status_code = 403
            raise QontoError("Qonto a refusé l'accès (HTTP 403).", response=response)

    result = qonto_sync.sync_bank_account(bank["ba"].id, client=Refusing())
    assert result["statements"] == 0 and len(result["errors"]) == 1
    assert result["errors"][0].startswith("Relevés de compte : ")
    assert db.session.get(BankAccount, bank["ba"].id).qonto_synced_at is not None  # synchronisation enregistrée


# ------------------------------------------------------------------ lot RQ3 : dépôt pour un compte hors Qonto

def _other(bank):
    other = BankAccount(label="Crédit Agricole", account_id=bank["ba"].account_id)
    db.session.add(other)
    db.session.commit()
    return other


def _post(client, ba_id, period, content, name="releve.pdf"):
    import io
    data = {"period": period, "file": (io.BytesIO(content), name)} if content is not None else {"period": period}
    return client.post(f"/api/v1/bank-accounts/{ba_id}/statements", data=data, content_type="multipart/form-data")


def test_upload_on_a_non_qonto_account_then_replace(bank, monkeypatch):
    client, other = bank["client"], _other(bank)
    monkeypatch.setattr(bank_statements, "upload_months",
                        lambda today=None, _u=bank_statements.upload_months: _u(TODAY))
    months = client.get(f"/api/v1/bank-accounts/{other.id}/statements").get_json()["upload_months"]
    assert months == ["2026-11", "2026-10", "2026-09", "2026-08", "2026-07"]
    resp = _post(client, other.id, "2026-10", PDF_V1, "CA-octobre.pdf")
    assert resp.status_code == 201 and resp.get_json()["notices"][0]["message"] == "Relevé de 10/2026 déposé."
    statement = BankStatement.query.filter_by(bank_account_id=other.id).one()
    assert statement.source == "upload" and statement.file_name == "CA-octobre.pdf"
    assert statement.file_path == f"releves/{other.id}/2026-10.pdf"
    assert _post(client, other.id, "2026-10", PDF_V2).get_json()["notices"][0]["message"] == "Relevé de 10/2026 remplacé."
    db.session.refresh(statement)
    assert statement.replaced_at is not None and bank_statements.path_for(statement).read_bytes() == PDF_V2
    assert BankStatement.query.count() == 1


def test_upload_refusals(bank, monkeypatch):
    client, other = bank["client"], _other(bank)
    monkeypatch.setattr(bank_statements, "upload_months",
                        lambda today=None, _u=bank_statements.upload_months: _u(TODAY))
    assert client.get(f"/api/v1/bank-accounts/{bank['ba'].id}/statements").get_json()["upload_months"] == []
    cases = [
        (bank["ba"].id, "2026-10", PDF_V1, "rattaché à Qonto"),
        (other.id, "2026-12", PDF_V1, "n'appartient pas"),     # mois pas commencé
        (other.id, "2025-10", PDF_V1, "n'appartient pas"),     # hors exercice ouvert
        (other.id, "octobre", PDF_V1, "Choisissez le mois"),
        (other.id, "2026-10", None, "Choisissez le fichier"),
        (other.id, "2026-10", b"GIF89a", "n'est pas un PDF"),
    ]
    for ba_id, period, content, message in cases:
        resp = _post(client, ba_id, period, content)
        assert resp.status_code == 422 and message in resp.get_json()["error"]["message"], (period, resp.get_json())
    assert BankStatement.query.count() == 0


def test_accountant_cannot_upload(app, login_as, monkeypatch, tmp_path):
    bank = _bank(app, login_as, monkeypatch, tmp_path, role="accountant")
    other = _other(bank)
    assert _post(bank["client"], other.id, "2026-10", PDF_V1).status_code == 403


# ------------------------------------------------------------------ lot RQ4 : archive pour l'expert-comptable

def _zip(resp):
    import io
    import zipfile
    return zipfile.ZipFile(io.BytesIO(resp.data))


def test_accountant_archive_without_fec(bank, monkeypatch):
    """Exercice ouvert (pas de FEC) : relevés de l'exercice et LISEZMOI avec les mois manquants."""
    monkeypatch.setattr(bank_statements, "accountant_archive",
                        lambda fy, f, r=None, _a=bank_statements.accountant_archive: _a(fy, f, r, TODAY))
    bank_statements.fetch_qonto(bank["ba"])
    other = _other(bank)
    fy = FiscalYear.query.one()
    resp = bank["client"].get(f"/fiscal-years/{fy.id}/accountant-archive.zip")
    assert resp.status_code == 200 and resp.mimetype == "application/zip"
    assert "expert-comptable-2026-2027.zip" in resp.headers["Content-Disposition"]
    archive = _zip(resp)
    folder = "releves/Qonto_Compte_principal"
    assert sorted(archive.namelist()) == ["LISEZMOI.txt", f"{folder}/2026-07.pdf", f"{folder}/2026-09.pdf",
                                          f"{folder}/2026-10.pdf"]
    assert archive.read(f"{folder}/2026-07.pdf") == PDF_V1
    readme = archive.read("LISEZMOI.txt").decode()
    assert "FEC : absent — " in readme and ".." not in readme
    assert "Qonto — Compte principal : 3 relevé(s) ; manquant(s) : 08/2026" in readme
    assert f"{other.label} : 0 relevé(s) ; manquant(s) : 07/2026, 08/2026, 09/2026, 10/2026" in readme


def test_accountant_archive_with_fec_and_accountant_role(app, login_as, monkeypatch, tmp_path):
    from app.views import fec as fec_view
    bank = _bank(app, login_as, monkeypatch, tmp_path, role="accountant")
    monkeypatch.setattr(fec_view, "fec_content", lambda fy: (b"JournalCode|JournalLib\r\n", "808534283FEC20270630.txt"))
    fy = FiscalYear.query.one()
    resp = bank["client"].get(f"/fiscal-years/{fy.id}/accountant-archive.zip")  # lecture : le comptable y a droit
    assert resp.status_code == 200
    archive = _zip(resp)
    assert archive.read("808534283FEC20270630.txt").startswith(b"JournalCode")
    assert "FEC : 808534283FEC20270630.txt" in archive.read("LISEZMOI.txt").decode()
    assert bank["client"].get("/fiscal-years/999/accountant-archive.zip").status_code == 404
