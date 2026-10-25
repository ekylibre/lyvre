"""Lot B.1 : adresse et nature des tiers ; paramètres des reçus fiscaux (activation par
l'administrateur de l'instance, déclaration de responsabilité, mentions obligatoires, signature)."""
from io import BytesIO

import pytest

from app.extensions import db
from app.models import Account, Entity, Instance, ReceiptSettings
from app.services import organization

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _error(resp, status):
    assert resp.status_code == status, resp.get_json()
    return resp.get_json()["error"]


@pytest.fixture()
def ready(app, tmp_path, monkeypatch):
    """Structure complète et compte de dons 7541 ; signature à déposer."""
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    db.session.add(Account(code="7541", label="Dons manuels", account_type="REVENUE"))
    db.session.commit()
    org = organization.get()
    org.name, org.rna, org.purpose = "Les Amis du Jardin", "W123456789", "Jardinage partagé"
    org.address_line1, org.postal_code, org.city = "1 rue des Lilas", "35000", "Rennes"
    org.signatory_name, org.signatory_title = "Camille Martin", "Présidente"
    db.session.commit()


def _upload(client, body=PNG, name="sig.png"):
    return client.post("/api/v1/receipts/settings/signature", data={"signature": (BytesIO(body), name)},
                       content_type="multipart/form-data")


def test_entity_address_and_kind(app, login_as):
    client = login_as()
    created = client.post("/api/v1/tiers", json={"name": "Dupont", "person_kind": "individual",
                                                  "address_line1": "2 place Ste-Anne", "postal_code": "35000",
                                                  "city": "Rennes"}).get_json()["item"]
    assert (created["person_kind"], created["city"]) == ("individual", "Rennes")
    entity_id = created["id"]
    # Une modification sans les champs d'adresse (autres écrans) ne les efface pas.
    client.patch(f"/api/v1/tiers/{entity_id}", json={"name": "Dupont Jean"})
    entity = db.session.get(Entity, entity_id)
    assert (entity.address_line1, entity.person_kind) == ("2 place Ste-Anne", "individual")
    assert _error(client.patch(f"/api/v1/tiers/{entity_id}", json={"name": "Dupont", "postal_code": "3500"}),
                  422)["fields"] == {"postal_code": "Code postal français : 5 chiffres."}
    assert client.patch(f"/api/v1/tiers/{entity_id}", json={"name": "Dupont", "postal_code": "B-1000",
                                                            "country": "Belgique"}).status_code == 200
    _error(client.patch(f"/api/v1/tiers/{entity_id}", json={"name": "Dupont", "person_kind": "robot"}), 422)


def test_activation_requires_mentions_and_acknowledgement(app, login_as, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    client = login_as(role="admin")
    settings = client.get("/api/v1/receipts/settings").get_json()["item"]
    assert settings["enabled"] is False and settings["donation_prefixes"] == ["7541"]
    assert {r["key"]: r["ok"] for r in settings["readiness"]}["identity"] is False
    error = _error(client.put("/api/v1/receipts/settings", json={
        "enabled": True, "eligibility": "general_interest", "cgi_articles": ["200"], "donation_prefixes": ["7541"],
        "acknowledged": True}), 422)
    assert error["message"].startswith("Activation impossible") and "Adresse de la structure" in error["message"]
    assert ReceiptSettings.query.one().enabled is False


def test_full_activation_flow(ready, login_as):
    client = login_as(role="admin")
    body = {"enabled": True, "eligibility": "general_interest", "cgi_articles": ["200", "238bis"],
            "donation_prefixes": ["7541"]}
    assert "Image de la signature" in _error(client.put("/api/v1/receipts/settings", json=body), 422)["message"]
    assert _upload(client).status_code == 200
    assert client.get("/receipts/signature").data == PNG
    assert "responsabilité" in _error(client.put("/api/v1/receipts/settings", json=body), 422)["message"]
    item = client.put("/api/v1/receipts/settings", json={**body, "acknowledged": True}).get_json()["item"]
    assert item["enabled"] and item["acknowledged_at"] and item["cgi_articles"] == ["200", "238bis"]
    assert all(r["ok"] for r in item["readiness"])
    assert item["donation_accounts"] == [{"code": "7541", "label": "Dons manuels"}]
    # Changer l'éligibilité impose une nouvelle déclaration.
    _error(client.put("/api/v1/receipts/settings", json={**body, "eligibility": "public_utility"}), 422)
    assert "cas prévu" in _error(client.put("/api/v1/receipts/settings", json={**body, "eligibility": "other",
                                                                                "acknowledged": True}), 422)["message"]
    # Sans signature, plus d'émission possible : désactivation.
    assert client.delete("/api/v1/receipts/settings/signature").get_json()["item"]["enabled"] is False
    assert client.get("/receipts/signature").status_code == 404


def test_signature_and_inputs_validation(ready, login_as):
    client = login_as(role="admin")
    assert "PNG ou JPEG" in _error(_upload(client, b"GIF89a....", "sig.gif"), 422)["message"]
    assert "500 Ko" in _error(_upload(client, PNG + b"\x00" * 600 * 1024), 422)["message"]
    _error(client.put("/api/v1/receipts/settings", json={"cgi_articles": ["999"]}), 422)
    _error(client.put("/api/v1/receipts/settings", json={"donation_prefixes": ["512"]}), 422)
    _error(client.put("/api/v1/receipts/settings", json={"eligibility": "autre"}), 422)


def test_only_instance_admin_changes_settings(ready, login_as):
    client = login_as(role="treasurer")
    assert client.get("/api/v1/receipts/settings").status_code == 200
    _error(client.put("/api/v1/receipts/settings", json={"enabled": False}), 403)
    _error(_upload(client), 403)


def test_sci_has_no_receipts(app, login_as):
    client = login_as(role="admin")
    Instance.query.one().chart = "sci"
    db.session.commit()
    assert _error(client.get("/api/v1/receipts/settings"), 403)["code"] == "association_only"
