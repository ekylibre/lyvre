"""Intégration SUPER PDP (lot PDP1) : une seule plateforme agréée à la fois (Qonto › Ventes ou SUPER PDP),
envoi d'une facture Factur-X, réception d'une facture d'achat, statuts. Faux client : aucun appel réseau."""
import facturx
import pytest

from app.extensions import db
from app.models import Purchase, Sale
from app.services import external_config, sale_documents, superpdp
from test_sales import API, _draft, admin  # noqa: F401


class FakeClient:
    def __init__(self, received=None):
        self.sent, self.received, self.events = [], received or [], {}

    def send_invoice(self, content, external_id, mime="application/pdf"):
        self.sent.append((content, external_id))
        return {"id": 42, "direction": "out", "events": [{"id": 1, "status_code": "api:uploaded", "created_at": "2026-11-08T10:00:00Z"}]}

    def invoices(self, direction, starting_after_id=None, limit=50):
        items = [i for i, _c in self.received if not starting_after_id or i["id"] > starting_after_id]
        return {"data": items, "has_after": False}

    def download(self, invoice_id):
        return next(c for i, c in self.received if i["id"] == invoice_id), "application/pdf"

    def events_of(self, invoice_id):
        return self.events.get(invoice_id, [])


@pytest.fixture()
def pdp(admin):  # noqa: F811
    external_config.set_many("superpdp", {"client_id": "app-123", "client_secret": "secret"})
    external_config.set_enabled("superpdp", True)
    return admin


def _issued(client):
    item = _draft(client)
    assert client.post(f"{API}/{item['id']}/issue").status_code == 200
    return db.session.get(Sale, item["id"])


def test_one_platform_at_a_time(admin):  # noqa: F811
    external_config.set_scopes("qonto", ["transactions", "purchases", "sales"])
    resp = admin.post("/api/v1/integrations/superpdp/enabled", json={"enabled": True})
    assert resp.status_code == 409 and "qu'une plateforme agréée" in resp.get_json()["error"]["message"]
    external_config.set_scopes("qonto", ["transactions", "purchases"])           # Qonto garde la banque et les achats
    assert admin.post("/api/v1/integrations/superpdp/enabled", json={"enabled": True}).status_code == 200
    assert external_config.acting_pdp() == "superpdp"
    resp = admin.post("/api/v1/integrations/qonto/scopes", json={"scopes": ["transactions", "purchases", "sales"]})
    assert resp.status_code == 409 and "SUPER PDP l'est déjà" in resp.get_json()["error"]["message"]
    external_config.set_scopes("superpdp", [])                                    # plus de rôle de plateforme
    assert admin.post("/api/v1/integrations/qonto/scopes", json={"scopes": ["sales"]}).status_code == 200
    assert external_config.acting_pdp() == "qonto"


def test_send_invoice_and_follow_status(pdp, monkeypatch):
    sale = _issued(pdp)
    fake = FakeClient()
    monkeypatch.setattr(superpdp, "_client", lambda: fake)
    resp = pdp.post(f"{API}/{sale.id}/superpdp")
    assert resp.status_code == 200, resp.get_json()
    item = resp.get_json()["item"]
    assert item["pdp"]["id"] == "42" and item["pdp"]["status_label"] == "Déposée"
    content, external_id = fake.sent[0]
    _name, xml = facturx.get_xml_from_pdf(content, check_xsd=True)
    assert b"F-2026-0001" in xml and external_id.endswith(f"-sale-{sale.id}")
    assert pdp.post(f"{API}/{sale.id}/superpdp").status_code == 409                # déjà transmise
    fake.events[42] = [{"id": 1, "status_code": "api:uploaded", "created_at": "2026-11-08T10:00:00Z"},
                       {"id": 2, "status_code": "fr:205", "status_text": "Approuvée", "created_at": "2026-11-09T10:00:00Z"}]
    result = superpdp.sync(client=fake)
    assert result["statuses"] == 1 and db.session.get(Sale, sale.id).pdp_status == "fr:205"


def test_send_requires_the_scope(pdp):
    sale = _issued(pdp)
    external_config.set_scopes("superpdp", ["receive"])
    resp = pdp.post(f"{API}/{sale.id}/superpdp")
    assert resp.status_code == 409 and resp.get_json()["error"]["code"] == "integration_required"


def test_receive_supplier_invoice(pdp, monkeypatch, app, tmp_path):
    from app.models import Organization
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    sale = _issued(pdp)                                         # une facture Factur-X réelle sert de facture reçue
    content = sale_documents.render_pdf(sale)
    fake = FakeClient(received=[({"id": 7, "direction": "in", "events": [{"id": 3, "status_code": "fr:202",
                                                                            "created_at": "2026-11-08T10:00:00Z"}]}, content)])
    result = superpdp.sync(client=fake)
    assert result["created"] == 1 and result["read"] == 1
    purchase = Purchase.query.filter_by(pdp_id="7").one()
    assert (purchase.source, purchase.is_einvoice, purchase.invoice_number, purchase.total_cents) == ("superpdp", True, "F-2026-0001", 26852)
    assert purchase.supplier_name == Organization.query.first().name and purchase.pdp_status == "fr:202"
    assert purchase.attachment_path.endswith(".pdf") and sum(l.total_cents for l in purchase.lines) == 26852
    assert superpdp.sync(client=fake)["created"] == 0                                # déjà reçue
    listed = pdp.get("/api/v1/purchases?source=superpdp").get_json()
    assert [p["pdp_status"] for p in listed["items"]] == ["fr:202"] and listed["meta"]["superpdp"]["enabled"]


def test_probe_reports_company_and_directory(pdp, monkeypatch):
    from app.services import integrations, superpdp_client

    class Probe(superpdp_client.SuperPdpClient):
        def company(self):
            return {"formal_name": "SCI Exemple", "number_scheme": "fr_siren", "number": "123456789", "env": "sandbox"}

        def directory_entries(self):
            return [{"identifier": "0225:123456789", "status": "error", "is_replyto": False},
                    {"identifier": "0225:123456789_replyto", "status": "created", "is_replyto": True}]

    monkeypatch.setattr(superpdp_client, "SuperPdpClient", Probe)
    result = integrations.run_check("superpdp")
    assert result.ok, result.message
    assert "SCI Exemple" in result.message and "bac à sable" in result.message and "en erreur (portabilité" in result.message
