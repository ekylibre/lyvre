"""Lot L4 : signature des baux avec Docuseal (faux client, aucun appel réel) — signataires (gérants
puis preneur), PDF envoyé avec les balises de signature, suivi, PDF signé et journal d'audit,
annulation, verrou du bail envoyé, intégration requise."""
from datetime import date
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.extensions import db
from app.models import Entity, Instance, Lease, LeaseSignature
from app.services import docuseal, external_config, lease_signatures
from test_lease_wizard import _tenant, admin  # noqa: F401  (fixture)

API = "/api/v1/leases"


class FakeDocuseal:
    """Serveur Docuseal simulé : garde le dernier envoi, statuts réglables."""

    def __init__(self):
        self.created, self.archived, self.status, self.submitters = [], [], "pending", {}
        self.fail = None

    def create_submission(self, name, pdf, submitters, external_id):
        if self.fail:
            raise docuseal.DocusealError(self.fail)
        self.created.append({"name": name, "pdf": pdf, "submitters": submitters, "external_id": external_id})
        self.submitters = {s["role"]: {"id": 100 + i, "role": s["role"], "status": "sent" if i == 0 else "awaiting",
                                       "submission_id": 77} for i, s in enumerate(submitters)}
        return {"id": 77, "submitters": list(self.submitters.values())}

    def submission(self, submission_id):
        if self.fail:
            raise docuseal.DocusealError(self.fail)
        return {"id": submission_id, "status": self.status, "submitters": list(self.submitters.values()),
                "completed_at": "2026-10-25T09:30:00.000Z" if self.status == "completed" else None,
                "audit_log_url": "https://docuseal.exemple.org/blobs/audit.pdf"}

    def documents(self, submission_id):
        return [{"name": "bail", "url": "https://docuseal.exemple.org/blobs/signed.pdf"}]

    def download(self, url):
        return b"%PDF-signed " + url.encode()

    def archive(self, submission_id):
        self.archived.append(submission_id)


@pytest.fixture()
def fake(monkeypatch, app, tmp_path):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    client = FakeDocuseal()
    monkeypatch.setattr(docuseal.Client, "from_config", classmethod(lambda cls, timeout=30: client))
    external_config.set_many("docuseal", {"url": "https://docuseal.exemple.org", "api_key": "cle-de-test"})
    db.session.commit()
    return client


def _active_lease(admin, managers=("Gérante Dupont",)):  # noqa: F811
    Instance.query.one().has_associates = True
    db.session.commit()
    for name in managers:
        resp = admin.post("/api/v1/associates", json={"new_name": name, "is_manager": True})
        assert resp.status_code == 201, resp.get_json()
        Entity.query.filter_by(name=name).one().email = f"{name.split()[-1].lower()}@exemple.org"
        db.session.commit()
    lease = admin.post(API, json={"draft": True, "entity_id": _tenant().id, "unit_label": "La Vauzelle",
                                  "kind": "derogatory", "start_date": date.today().isoformat()}).get_json()["item"]
    admin.post(f"{API}/{lease['id']}/items", json={"label": "Bureau", "nature": "building", "area_m2": 40, "unit_price": "2"})
    assert admin.post(f"{API}/{lease['id']}/activate", json={"frequency": "yearly"}).status_code == 200
    return lease["id"]


def test_send_with_signature_tags_then_complete(admin, fake):  # noqa: F811
    lease_id = _active_lease(admin, ("Gérante Dupont", "Gérant Martin"))
    detail = admin.get(f"{API}/{lease_id}").get_json()["item"]
    assert [s["role"] for s in detail["signers_planned"]] == ["Bailleur 1", "Bailleur 2", "Preneur"]
    assert detail["signature_problems"] == [] and detail["signature"] is None and detail["locked"] is False

    resp = admin.post(f"{API}/{lease_id}/signature")
    assert resp.status_code == 200, resp.get_json()
    item = resp.get_json()["item"]
    assert item["locked"] is True and item["signature"]["status"] == "sent"
    assert [(s["role"], s["email"], s["status"]) for s in item["signature"]["signers"]] == [
        ("Bailleur 1", "dupont@exemple.org", "sent"), ("Bailleur 2", "martin@exemple.org", "awaiting"),
        ("Preneur", "preneur@example.org", "awaiting")]
    sent = fake.created[0]
    assert sent["external_id"] == f"lease-{lease_id}" and [s["role"] for s in sent["submitters"]] == [
        "Bailleur 1", "Bailleur 2", "Preneur"]
    text = "".join(page.extract_text() for page in PdfReader(BytesIO(sent["pdf"])).pages)
    for key, role in (("L1", "Bailleur 1"), ("L2", "Bailleur 2"), ("T", "Preneur")):
        assert f"{{{{Signature {key};role={role};type=signature;width=170;height=55}}}}" in text
    assert admin.get(item["signature"]["files"]["sent"]).data == sent["pdf"]

    # Bail envoyé : termes, lignes, texte et facturation verrouillés.
    for call in (lambda: admin.patch(f"{API}/{lease_id}", json={"unit_label": "Autre"}),
                 lambda: admin.post(f"{API}/{lease_id}/items", json={"label": "Cave"}),
                 lambda: admin.put(f"{API}/{lease_id}/document", json={"body_html": "<p>x</p>"}),
                 lambda: admin.post(f"{API}/{lease_id}/document/regenerate"),
                 lambda: admin.post(f"{API}/{lease_id}/activate", json={}),
                 lambda: admin.post(f"{API}/{lease_id}/signature")):
        resp = call()
        assert resp.status_code == 409, resp.get_json()
    assert admin.patch(f"{API}/{lease_id}", json={"active": False}).status_code == 200  # fin du bail : permise

    for submitter in fake.submitters.values():
        submitter.update(status="completed", completed_at="2026-10-25T09:30:00.000Z")
    fake.status = "completed"
    item = admin.post(f"{API}/{lease_id}/signature/refresh").get_json()["item"]
    sig = item["signature"]
    assert sig["status"] == "completed" and sig["completed_at"].startswith("2026-10-25T09:30")
    assert all(s["signed_at"] for s in sig["signers"]) and set(sig["files"]) == {"sent", "signed", "audit"}
    assert admin.get(sig["files"]["signed"]).data.startswith(b"%PDF-signed https://docuseal.exemple.org/blobs/signed.pdf")
    assert admin.patch(f"{API}/{lease_id}", json={"unit_label": "Autre"}).get_json()["error"]["message"] == \
        "Bail signé : il ne se modifie plus."


def test_declined_cancel_and_resend(admin, fake):  # noqa: F811
    lease_id = _active_lease(admin)
    admin.post(f"{API}/{lease_id}/signature")
    fake.submitters["Preneur"].update(status="declined", declined_at="2026-10-25T10:00:00.000Z")
    item = admin.post(f"{API}/{lease_id}/signature/refresh").get_json()["item"]
    assert item["signature"]["status"] == "declined" and item["locked"] is False
    assert admin.delete(f"{API}/{lease_id}/signature").status_code == 409  # refusé : rien à annuler

    resp = admin.post(f"{API}/{lease_id}/signature")  # renvoi après correction
    assert resp.status_code == 200 and len(fake.created) == 2
    resp = admin.delete(f"{API}/{lease_id}/signature")
    assert resp.status_code == 200 and fake.archived == ["77"]
    item = resp.get_json()["item"]
    assert item["signature"]["status"] == "declined" and item["locked"] is False  # dernier envoi non annulé
    assert [s.status for s in LeaseSignature.query.order_by(LeaseSignature.id)] == ["declined", "cancelled"]


def test_refresh_on_open_is_throttled_and_errors_kept(admin, fake):  # noqa: F811
    lease_id = _active_lease(admin)
    admin.post(f"{API}/{lease_id}/signature")
    sig = LeaseSignature.query.one()
    calls = []
    original = fake.submission
    fake.submission = lambda sid: calls.append(sid) or original(sid)
    admin.get(f"{API}/{lease_id}")
    assert calls == []  # relu il y a moins d'une minute
    sig.checked_at = sig.checked_at.replace(year=2000)
    db.session.commit()
    fake.fail = "Le serveur Docuseal https://docuseal.exemple.org ne répond pas."
    item = admin.get(f"{API}/{lease_id}").get_json()["item"]  # la fiche s'affiche malgré l'erreur
    assert item["signature"]["error"] == fake.fail and item["signature"]["status"] == "sent"
    assert admin.post(f"{API}/{lease_id}/signature/refresh").status_code == 502


def test_send_refused_without_managers_email_or_integration(admin, fake):  # noqa: F811
    lease_id = _active_lease(admin, managers=())
    resp = admin.post(f"{API}/{lease_id}/signature")
    assert resp.status_code == 409 and "Aucun gérant" in resp.get_json()["error"]["message"]
    _tenant().email = None
    db.session.commit()
    problems = admin.get(f"{API}/{lease_id}").get_json()["item"]["signature_problems"]
    assert any("E-mail manquant sur la fiche du preneur" in p for p in problems)

    draft = admin.post(API, json={"draft": True, "entity_id": _tenant().id, "unit_label": "Brouillon",
                                  "start_date": date.today().isoformat()}).get_json()["item"]
    assert admin.post(f"{API}/{draft['id']}/signature").status_code == 409

    fake.fail = "Clé d'API Docuseal refusée : vérifiez l'intégration."
    Entity.query.filter_by(name="Association Preneuse").one().email = "preneur@example.org"
    db.session.commit()
    admin.post("/api/v1/associates", json={"new_name": "Gérante Rose", "is_manager": True})
    Entity.query.filter_by(name="Gérante Rose").one().email = "rose@exemple.org"
    db.session.commit()
    resp = admin.post(f"{API}/{lease_id}/signature")
    assert resp.status_code == 502 and "refusée" in resp.get_json()["error"]["message"]
    assert LeaseSignature.query.count() == 0

    instance = Instance.query.one()
    instance.integrations = '{"enabled": [], "dismissed": []}'
    db.session.commit()
    assert admin.post(f"{API}/{lease_id}/signature").get_json()["error"]["code"] == "integration_required"


def test_old_text_gets_a_signature_page(app):
    signers = [{"key": "l1", "role": "Bailleur 1", "name": "A"}, {"key": "t", "role": "Preneur", "name": "B"}]
    body = lease_signatures.with_tags("<p>Texte</p><div class='sign-box sign-t'></div>", signers)
    assert "{{Signature T;role=Preneur" in body and "signature-page" in body
    assert body.index("Signature T;") < body.index("signature-page") < body.index("Signature L1;")


def test_client_paths_and_download_host():
    selfhosted = docuseal.Client("https://docuseal.seconde-nature.net/", "k")
    assert selfhosted.api == "https://docuseal.seconde-nature.net/api"
    cloud = docuseal.Client("https://api.docuseal.eu", "k")
    assert cloud.api == "https://api.docuseal.eu" and "docuseal.eu" in cloud.file_hosts
    with pytest.raises(docuseal.DocusealError):
        selfhosted.download("https://ailleurs.example.org/x.pdf")
    with pytest.raises(docuseal.DocusealError):
        docuseal.Client("", "k")
