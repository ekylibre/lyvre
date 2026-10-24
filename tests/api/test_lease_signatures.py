"""Lot L4 : signature des baux avec Documenso (faux client, aucun appel réel) — signataires (gérants
puis preneur), PDF envoyé avec les balises de signature, suivi, PDF signé et journal d'audit,
annulation, verrou du bail envoyé, intégration requise."""
from datetime import date
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.extensions import db
from app.models import Entity, Instance, Lease, LeaseSignature
from app.services import documenso, external_config, lease_signatures
from test_lease_wizard import _tenant, admin  # noqa: F401  (fixture)

API = "/api/v1/leases"


class FakeDocumenso:
    """Serveur Documenso simulé : garde les envois, statuts réglables."""

    def __init__(self):
        self.created, self.distributed, self.cancelled, self.deleted = [], [], [], []
        self.status, self.recipients, self.fail, self.fail_distribute = "PENDING", [], None, None
        self.fields_found, self.resized = None, None

    def create_envelope(self, title, pdf, recipients, external_id, send_email=True):
        if self.fail:
            raise documenso.DocumensoError(self.fail)
        self.created.append({"title": title, "pdf": pdf, "recipients": recipients, "external_id": external_id})
        self.recipients = [{"id": 500 + n, "email": r["email"], "name": r["name"], "signingOrder": n,
                            "signingStatus": "NOT_SIGNED", "readStatus": "NOT_OPENED", "sendStatus": "NOT_SENT"}
                           for n, r in enumerate(recipients, start=1)]
        return f"envelope_{len(self.created)}"

    def resize_signatures(self, envelope_id, width, height):
        self.resized = (envelope_id, width, height)
        return self.fields_found if self.fields_found is not None else len(self.recipients)

    def add_initials(self, envelope_id, pages, boxes):
        self.initials = (envelope_id, pages, boxes)
        return pages * len(boxes)

    def distribute(self, envelope_id):
        if self.fail_distribute:
            raise documenso.DocumensoError(self.fail_distribute)
        self.distributed.append(envelope_id)
        self.recipients[0]["sendStatus"] = "SENT"  # signature dans l'ordre : le premier seulement
        return {}

    def envelope(self, envelope_id):
        if self.fail:
            raise documenso.DocumensoError(self.fail)
        return {"id": envelope_id, "status": self.status, "recipients": self.recipients,
                "completedAt": "2026-10-25T09:30:00.000Z" if self.status == "COMPLETED" else None,
                "envelopeItems": [{"id": "item_1"}]}

    def download_signed(self, item_id):
        return b"%PDF-signed " + item_id.encode()

    def audit_log(self, envelope_id):
        return b"%PDF-audit " + envelope_id.encode()

    def cancel(self, envelope_id):
        self.cancelled.append(envelope_id)

    def delete(self, envelope_id):
        self.deleted.append(envelope_id)


@pytest.fixture()
def fake(monkeypatch, app, tmp_path):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    client = FakeDocumenso()
    monkeypatch.setattr(documenso.Client, "from_config", classmethod(lambda cls, timeout=30: client))
    external_config.set_many("documenso", {"url": "https://signature.exemple.org", "api_key": "api_test"})
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
    assert sent["external_id"] == f"lease-{lease_id}-1" and fake.distributed == ["envelope_1"]
    assert fake.resized == ("envelope_1", 32.0, 7.0)
    pages = len(PdfReader(BytesIO(sent["pdf"])).pages)
    assert fake.initials == ("envelope_1", pages, [(62.4, 93.0, 9.0, 2.6), (72.4, 93.0, 9.0, 2.6), (82.4, 93.0, 9.0, 2.6)])
    assert [r["email"] for r in sent["recipients"]] == ["dupont@exemple.org", "martin@exemple.org", "preneur@example.org"]
    text = "".join(page.extract_text() for page in PdfReader(BytesIO(sent["pdf"])).pages)
    for n in (1, 2, 3):
        assert f"{{{{signature, r{n}}}}}" in text
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

    for r in fake.recipients:
        r.update(signingStatus="SIGNED", readStatus="OPENED", sendStatus="SENT", signedAt="2026-10-25T09:20:00.000Z")
    fake.status = "COMPLETED"
    item = admin.post(f"{API}/{lease_id}/signature/refresh").get_json()["item"]
    sig = item["signature"]
    assert sig["status"] == "completed" and sig["completed_at"].startswith("2026-10-25T09:30")
    assert all(s["signed_at"].startswith("2026-10-25T09:20") for s in sig["signers"])
    assert set(sig["files"]) == {"sent", "signed", "audit"}
    assert admin.get(sig["files"]["signed"]).data == b"%PDF-signed item_1"
    assert admin.get(sig["files"]["audit"]).data == b"%PDF-audit envelope_1"
    assert admin.patch(f"{API}/{lease_id}", json={"unit_label": "Autre"}).get_json()["error"]["message"] == \
        "Bail signé : il ne se modifie plus."


def test_declined_cancel_and_resend(admin, fake):  # noqa: F811
    lease_id = _active_lease(admin)
    admin.post(f"{API}/{lease_id}/signature")
    fake.recipients[-1]["signingStatus"] = "REJECTED"
    fake.status = "REJECTED"
    item = admin.post(f"{API}/{lease_id}/signature/refresh").get_json()["item"]
    assert item["signature"]["status"] == "declined" and item["locked"] is False
    assert item["signature"]["signers"][-1]["status"] == "declined"
    assert admin.delete(f"{API}/{lease_id}/signature").status_code == 409  # refusé : rien à annuler

    resp = admin.post(f"{API}/{lease_id}/signature")  # renvoi après correction
    assert resp.status_code == 200 and len(fake.created) == 2
    resp = admin.delete(f"{API}/{lease_id}/signature")
    assert resp.status_code == 200 and fake.cancelled == ["envelope_2"]
    item = resp.get_json()["item"]
    assert item["signature"]["status"] == "declined" and item["locked"] is False  # dernier envoi non annulé
    assert [s.status for s in LeaseSignature.query.order_by(LeaseSignature.id)] == ["declined", "cancelled"]


def test_failed_distribution_leaves_nothing(admin, fake):  # noqa: F811
    lease_id = _active_lease(admin)
    fake.fail_distribute = "Documenso a refusé la demande (400)."
    resp = admin.post(f"{API}/{lease_id}/signature")
    assert resp.status_code == 502 and fake.deleted == ["envelope_1"]
    assert LeaseSignature.query.count() == 0 and admin.get(f"{API}/{lease_id}").get_json()["item"]["locked"] is False


def test_missing_signature_fields_stop_the_send(admin, fake):  # noqa: F811
    lease_id = _active_lease(admin)
    fake.fields_found = 1  # une balise non trouvée par Documenso
    resp = admin.post(f"{API}/{lease_id}/signature")
    assert resp.status_code == 502 and "cases de signature" in resp.get_json()["error"]["message"]
    assert fake.distributed == [] and fake.deleted == ["envelope_1"] and LeaseSignature.query.count() == 0


def test_refresh_on_open_is_throttled_and_errors_kept(admin, fake):  # noqa: F811
    lease_id = _active_lease(admin)
    admin.post(f"{API}/{lease_id}/signature")
    sig = LeaseSignature.query.one()
    calls = []
    original = fake.envelope
    fake.envelope = lambda eid: calls.append(eid) or original(eid)
    admin.get(f"{API}/{lease_id}")
    assert calls == []  # relu il y a moins d'une minute
    sig.checked_at = sig.checked_at.replace(year=2000)
    db.session.commit()
    fake.fail = "Le serveur Documenso https://signature.exemple.org ne répond pas."
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

    fake.fail = "Jeton d'API Documenso refusé : vérifiez l'intégration."
    Entity.query.filter_by(name="Association Preneuse").one().email = "preneur@example.org"
    db.session.commit()
    admin.post("/api/v1/associates", json={"new_name": "Gérante Rose", "is_manager": True})
    Entity.query.filter_by(name="Gérante Rose").one().email = "rose@exemple.org"
    db.session.commit()
    resp = admin.post(f"{API}/{lease_id}/signature")
    assert resp.status_code == 502 and "refusé" in resp.get_json()["error"]["message"]
    assert LeaseSignature.query.count() == 0

    instance = Instance.query.one()
    instance.integrations = '{"enabled": [], "dismissed": []}'
    db.session.commit()
    assert admin.post(f"{API}/{lease_id}/signature").get_json()["error"]["code"] == "integration_required"


def test_old_text_gets_a_signature_page(app):
    signers = [{"key": "l1", "role": "Bailleur 1", "name": "A"}, {"key": "t", "role": "Preneur", "name": "B"}]
    body = lease_signatures.with_tags("<p>Texte</p><div class='sign-box sign-t'></div>", signers)
    assert "{{signature, r2}}" in body and "signature-page" in body  # preneur : deuxième signataire
    assert body.index("{{signature, r2}}") < body.index("signature-page") < body.index("{{signature, r1}}")


def test_client_paths():
    client = documenso.Client("https://signature.seconde-nature.net/", "api_x")
    assert client.api == "https://signature.seconde-nature.net/api/v2"
    with pytest.raises(documenso.DocumensoError):
        documenso.Client("", "k")
