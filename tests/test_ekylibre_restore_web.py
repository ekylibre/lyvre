"""Imports › Sauvegarde Ekylibre (lot RE6) : dépôt, analyse et restauration en tâche de fond, instance vide exigée."""
import io

import pytest

from app.extensions import db
from conftest import _test_instance
from test_ekylibre_restore import _archive
from test_sync_jobs import ImmediateThread


@pytest.fixture()
def admin(app, login_as, tmp_path, monkeypatch):
    from app.models import Account
    from app.services import sync_jobs
    monkeypatch.setattr(sync_jobs.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(app, "instance_path", str(tmp_path / "instance"))
    _test_instance(chart="agri")
    for code, label, header in (("101", "Capital", True), ("164", "Emprunts", True), ("401", "Fournisseurs", True),
                                ("411", "Clients", True), ("445", "État TVA", True), ("512", "Banque", True),
                                ("601", "Achats", True), ("701", "Ventes", True)):
        db.session.add(Account(code=code, label=label, account_type="OTHER", is_header=header))
    db.session.commit()
    return login_as(is_admin=True)


def _upload(client, path, name="sauvegarde.zip"):
    return client.post("/api/v1/imports/ekylibre/upload", data={"file": (io.BytesIO(path.read_bytes()), name)},
                       content_type="multipart/form-data")


def test_upload_analyse_and_restore(admin, tmp_path):
    from app.models import JournalEntry, Purchase
    from app.models.bank_statement import BankStatement
    archive = _archive(tmp_path, extras=True)
    assert admin.get("/api/v1/imports/ekylibre").get_json()["item"]["archive"] is None
    response = _upload(admin, archive)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["item"]["archive"]["name"] == "sauvegarde.zip"
    assert admin.post("/api/v1/imports/ekylibre/run", json={}).status_code == 409        # analyse d'abord

    job = admin.post("/api/v1/imports/ekylibre/analyze", json={}).get_json()["job"]
    item = admin.get("/api/v1/imports/ekylibre").get_json()
    assert item["job"]["id"] == job["id"] and item["job"]["status"] == "done", item["job"]
    analysis = item["item"]["analysis"]
    assert analysis["blocking"] == 0 and analysis["chart"] == "agri" and analysis["period"]["start"] == "2025-01-01"
    assert analysis["volumes"]["entries"] == 4 and analysis["years"] == [2024, 2025]
    report = admin.get("/api/v1/imports/ekylibre/report")
    assert report.status_code == 200 and "analyse à blanc" in report.get_data(as_text=True)
    assert JournalEntry.query.count() == 0                                                  # rien d'écrit

    job = admin.post("/api/v1/imports/ekylibre/run", json={}).get_json()["job"]
    item = admin.get("/api/v1/imports/ekylibre").get_json()
    assert item["job"]["status"] == "done", item["job"]["message"]
    assert JournalEntry.query.filter_by(source_ref="AN-EKYLIBRE").count() == 1
    assert Purchase.query.one().attachment_name == "semences.pdf" and BankStatement.query.count() == 1
    state = item["item"]
    assert state["archive"] is None and state["imported"]["stats"]["purchases"] == 1 and state["report"]
    assert any("déjà" in b for b in state["blockers"])                                      # plus vide
    assert "import" in admin.get("/api/v1/imports/ekylibre/report").get_data(as_text=True)
    _upload(admin, archive)
    refused = admin.post("/api/v1/imports/ekylibre/analyze", json={})
    assert refused.status_code == 202                                                       # analyse permise
    assert admin.post("/api/v1/imports/ekylibre/run", json={}).status_code == 409           # import refusé


def test_upload_is_checked_and_discarded(admin, tmp_path):
    bad = tmp_path / "pas-un-zip.zip"
    bad.write_bytes(b"bonjour")
    assert _upload(admin, bad).status_code == 422
    text = tmp_path / "notes.txt"
    text.write_text("x")
    assert _upload(admin, text, "notes.txt").status_code == 422
    assert _upload(admin, _archive(tmp_path)).status_code == 200
    item = admin.delete("/api/v1/imports/ekylibre").get_json()["item"]
    assert item["archive"] is None and not item["report"]


def test_from_year_and_without_attachments(admin, tmp_path):
    from app.models import Purchase
    _upload(admin, _archive(tmp_path, extras=True))
    admin.post("/api/v1/imports/ekylibre/analyze", json={"from_year": 2024, "attachments": False})
    analysis = admin.get("/api/v1/imports/ekylibre").get_json()["item"]["analysis"]
    assert analysis["period"]["start"] == "2024-01-01" and analysis["options"]["attachments"] is False
    admin.post("/api/v1/imports/ekylibre/run", json={})
    assert Purchase.query.one().attachment_name is None


def test_restore_requires_admin(app, login_as):
    _test_instance(chart="agri")
    client = login_as(role="treasurer")
    assert client.get("/api/v1/imports/ekylibre").status_code == 403
