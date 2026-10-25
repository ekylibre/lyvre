"""Fonctions réservées aux associations (lot G1) : routes refusées à une autre structure (SCI),
données d'association ni calculées ni renvoyées, champs d'association ignorés à l'écriture, sans
rien effacer en base."""
from datetime import date

import pytest

from app.association_only import ASSOCIATION_ONLY_ENDPOINTS, is_association_only
from app.extensions import db
from app.models import ClosingStep, Entity, FiscalYear, Instance
from app.services import organization


def _error(resp, status):
    assert resp.status_code == status, (resp.status_code, resp.get_json())
    return resp.get_json()["error"]


def _sample_url(rule):
    values = {name: 1 if type(conv).__name__ == "IntegerConverter" else "x" for name, conv in rule._converters.items()}
    return rule.build(values, append_unknown=False)[1]


def _as(chart):
    Instance.query.filter_by(slug="test").one().chart = chart
    db.session.commit()


@pytest.fixture()
def sci(login_as):
    client = login_as(role="admin")
    _as("sci")
    return client


@pytest.fixture()
def asso(login_as):
    return login_as(role="admin")


def test_named_endpoints_exist(app):
    endpoints = {rule.endpoint for rule in app.url_map.iter_rules()}
    assert ASSOCIATION_ONLY_ENDPOINTS <= endpoints


def test_every_association_route_is_refused_to_a_sci(app, sci):
    """Garde-fou : toute route d'association, quelle que soit la méthode, est refusée à une SCI."""
    api, pages = [], []
    for rule in app.url_map.iter_rules():
        if not is_association_only(rule.endpoint):
            continue
        for method in sorted((rule.methods or set()) - {"HEAD", "OPTIONS"}):
            resp = sci.open(_sample_url(rule), method=method, json={})
            if rule.endpoint.startswith("api."):
                assert resp.status_code == 403, (method, rule.rule, resp.status_code)
                assert resp.get_json()["error"]["code"] == "association_only"
                api.append(rule.endpoint)
            else:
                assert resp.status_code == 404, (method, rule.rule, resp.status_code)
                pages.append(rule.endpoint)
    assert len(set(api)) > 60 and len(set(pages)) > 20
    assert {"api.receipts_list", "api.fiscal_years_dedicated_fund_add", "api.members_list", "api.helloasso_sync",
            "receipts.index", "entities.members", "exports.receipt_pdf"} <= set(api) | set(pages)


def test_common_routes_stay_open_to_a_sci(sci):
    assert sci.get("/api/v1/tiers").status_code == 200
    assert sci.get("/api/v1/organization").status_code == 200
    assert '<div id="root"></div>' in sci.get("/entities/").get_data(as_text=True)


def test_association_routes_open_to_an_association(asso):
    assert asso.get("/api/v1/receipts/settings").status_code == 200
    assert asso.get("/api/v1/members").status_code == 200
    assert '<div id="root"></div>' in asso.get("/entities/members").get_data(as_text=True)


def test_dashboard_members_only_for_an_association(asso):
    db.session.add(FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)))
    db.session.commit()
    assert asso.get("/api/v1/dashboard").get_json()["stats"]["new_members"] == 0
    _as("sci")
    assert asso.get("/api/v1/dashboard").get_json()["stats"]["new_members"] is None


def test_organization_ignores_the_other_structure_fields(asso):
    body = asso.put("/api/v1/organization", json={"name": "Asso", "rna": "W123456789", "signatory_name": "A. Martin",
                                                  "has_associates": True}).get_json()
    assert body["item"]["rna"] == "W123456789" and body["item"]["signatory_name"] == "A. Martin"
    assert body["item"]["has_associates"] is False  # une association n'a pas d'associés
    _as("sci")
    body = asso.put("/api/v1/organization", json={"name": "SCI", "rna": "", "signatory_name": "",
                                                  "has_associates": True}).get_json()
    assert body["item"]["has_associates"] is True
    org = organization.get()
    assert (org.name, org.rna, org.signatory_name) == ("SCI", "W123456789", "A. Martin")  # conservés


def test_tiers_membership_kept_and_hidden_for_a_sci(sci):
    member = Entity(name="Ancien adhérent", entity_type="AUTRE", is_member=True, is_benevole=True)
    db.session.add(member)
    db.session.commit()
    resp = sci.patch(f"/api/v1/tiers/{member.id}", json={"name": "Ancien adhérent", "entity_type": "AUTRE",
                                                          "is_member": False, "is_benevole": False,
                                                          "person_kind": "company"})
    assert resp.status_code == 200, resp.get_json()
    db.session.refresh(member)
    assert member.is_member and member.is_benevole  # rien n'est effacé
    assert member.person_kind == "company"          # la nature sert aussi aux baux et aux factures
    detail = sci.get(f"/api/v1/tiers/{member.id}").get_json()
    assert detail["work_times"] is None and detail["helloasso"] is None
    assert detail["item"]["last_helloasso_membership"] is None


def test_tiers_membership_written_for_an_association(asso):
    entity = Entity(name="Bénévole", entity_type="AUTRE")
    db.session.add(entity)
    db.session.commit()
    asso.patch(f"/api/v1/tiers/{entity.id}", json={"name": "Bénévole", "entity_type": "AUTRE",
                                                   "is_member": True, "is_benevole": True})
    db.session.refresh(entity)
    assert entity.is_member and entity.is_benevole
    detail = asso.get(f"/api/v1/tiers/{entity.id}").get_json()
    assert detail["work_times"] == [] and detail["helloasso"]["orders"] == []


def test_closing_without_dedicated_funds_for_a_sci(sci, tmp_path, monkeypatch, app):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    db.session.add(fy)
    db.session.commit()
    # Étape décidée quand la structure était une association : ignorée, sans être supprimée.
    db.session.add(ClosingStep(fiscal_year_id=fy.id, step="dedicated_funds", state="done"))
    db.session.commit()
    body = sci.get(f"/api/v1/fiscal-years/{fy.id}/closing").get_json()
    assert "dedicated_funds" not in [s["key"] for s in body["steps"]]
    assert body["dedicated_funds"] is None
    _error(sci.post(f"/api/v1/fiscal-years/{fy.id}/closing/dedicated_funds", json={"state": "done"}), 422)
    for step in ("checks", "inventory", "result", "fec"):
        db.session.add(ClosingStep(fiscal_year_id=fy.id, step=step, state="skipped", note="test"))
    db.session.commit()
    message = sci.post(f"/api/v1/fiscal-years/{fy.id}/close").get_json()
    assert "Fonds dédiés" not in str(message)
    assert ClosingStep.query.filter_by(fiscal_year_id=fy.id, step="dedicated_funds").count() == 1
