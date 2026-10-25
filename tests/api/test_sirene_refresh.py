"""Lot G5 : comparaison groupée des tiers avec Sirene (tâche de fond, sans réseau), revue, application
avec verrou optimiste, arrêt, droits."""
import pytest

from app.extensions import db
from app.models import Entity, Notification
from app.services import sirene, sirene_refresh, sync_jobs
from test_sirene import HEAD, POITIERS, UNIT, FakeResponse, insee  # noqa: F401  (fixture)
from test_sync_jobs import ImmediateThread

API = "/api/v1/entities/sirene-refresh"
NAME = UNIT["denominationUniteLegale"]


@pytest.fixture()
def batch(insee, monkeypatch):  # noqa: F811
    """Réponses multicritères : unités légales, établissements par SIRET, sièges par SIREN."""
    calls, routes = insee
    monkeypatch.setattr(sync_jobs.threading, "Thread", ImmediateThread)
    known = {"120027016": UNIT}
    routes[("POST", "/etat-courant/unites-legales/multicritere")] = lambda body: FakeResponse(
        200, {"items": [{"item": known[s]} for s in body["siren"] if s in known]})
    establishments = {"12002701600241": POITIERS, "12002701600563": HEAD}

    def etab(body):
        if body.get("etablissementSiege"):
            return FakeResponse(200, {"items": [{"item": HEAD}] if "120027016" in body["siren"] else []})
        return FakeResponse(200, {"items": [{"item": establishments[s]} for s in body["siret"] if s in establishments]})
    routes[("POST", "/etat-courant/etablissements/multicritere")] = etab
    poitiers = Entity(name="INSEE Poitiers", siret="12002701600241", city="Montrouge")
    head = Entity(name="Siège", siren="120027016")
    invalid = Entity(name="Numéro faux", siren="120027017")
    unknown = Entity(name="Inconnu", siren="552100554")
    without = Entity(name="Sans numéro")
    db.session.add_all([poitiers, head, invalid, unknown, without])
    db.session.commit()
    return calls, {"poitiers": poitiers, "head": head, "invalid": invalid, "unknown": unknown, "without": without}


def _items(body):
    return {i["name"]: i for i in body["result"]["items"]}


def test_compare_then_apply_with_optimistic_lock(login_as, batch):
    calls, e = batch
    client = login_as()
    resp = client.post(API, json={})
    assert resp.status_code == 202 and resp.get_json()["count"] == 4  # le tiers sans numéro n'est pas compté
    job_id = resp.get_json()["job"]["id"]
    # 1 paquet = 3 appels : unités légales, établissements (SIRET), sièges (SIREN seul).
    assert [(m, p, sorted(b) if b else None) for m, p, b in calls] == [
        ("POST", "/etat-courant/unites-legales/multicritere", ["nombre", "siren"]),
        ("POST", "/etat-courant/etablissements/multicritere", ["champs", "nombre", "siret"]),
        ("POST", "/etat-courant/etablissements/multicritere", ["champs", "etablissementSiege", "nombre", "siren"])]

    body = client.get(f"{API}/{job_id}").get_json()
    assert body["job"]["status"] == "done"
    items = _items(body)
    assert {n: i["state"] for n, i in items.items()} == {"INSEE Poitiers": "changes", "Siège": "changes",
                                                          "Numéro faux": "invalid", "Inconnu": "not_found"}
    changes = {c["field"]: c for c in items["INSEE Poitiers"]["changes"]}
    assert changes["city"] == {"field": "city", "label": "Ville", "current": "Montrouge", "proposed": "Poitiers",
                               "computed": False, "kind": "different"}
    assert changes["naf_code"]["kind"] == "empty" and changes["vat_number"]["computed"] is True
    assert "siret" not in changes and "siren" not in changes  # déjà identiques
    assert Entity.query.get(e["poitiers"].id).city == "Montrouge"  # rien n'est écrit avant la revue
    note = Notification.query.filter_by(job_id=job_id).one()
    assert note.url == f"/entities/sirene-review/{job_id}" and "2 tiers à revoir" in note.message

    # Entre la revue et l'application : la ville est changée à la main, un homonyme apparaît.
    e["poitiers"].city = "Lyon"
    db.session.add(Entity(name=NAME))
    db.session.commit()
    resp = client.post(f"{API}/{job_id}/apply", json={"changes": {
        str(e["poitiers"].id): ["city", "naf_code", "address_line1"], str(e["head"].id): ["name", "city"]}})
    assert resp.status_code == 200, resp.get_json()
    outcome = resp.get_json()
    assert outcome["applied"] == 3
    assert {(s["entity_id"], s["field"]) for s in outcome["skipped"]} == {(e["poitiers"].id, "city"), (e["head"].id, "name")}
    poitiers, head = Entity.query.get(e["poitiers"].id), Entity.query.get(e["head"].id)
    assert (poitiers.city, poitiers.naf_code, poitiers.naf_nomenclature, poitiers.address_line1) == \
        ("Lyon", "8411Z", "NAFRev2", "5 rue Sainte Catherine")
    assert (head.name, head.city) == ("Siège", "Montrouge")
    assert client.get(f"{API}/{job_id}").get_json()["applied"] is True


def test_selection_and_guards(login_as, batch):
    _calls, e = batch
    client = login_as()
    resp = client.post(API, json={"entity_ids": [e["head"].id]})
    assert resp.status_code == 202 and resp.get_json()["count"] == 1
    assert list(_items(client.get(f"{API}/{resp.get_json()['job']['id']}").get_json())) == ["Siège"]
    assert client.post(API, json={"entity_ids": [e["without"].id]}).status_code == 422
    assert client.post(API, json={"entity_ids": "1"}).status_code == 422
    assert client.get(f"{API}/999").status_code == 404
    from app.models import InstanceMembership
    InstanceMembership.query.one().role = "accountant"  # même utilisateur, devenu expert-comptable
    db.session.commit()
    assert client.post(API, json={}).status_code == 403
    assert client.get(f"{API}/{resp.get_json()['job']['id']}").status_code == 200  # consultation permise


def test_one_comparison_at_a_time(login_as, batch, monkeypatch):
    monkeypatch.setattr(sync_jobs.threading, "Thread", lambda **kwargs: type("T", (), {"start": lambda self: None})())
    client = login_as()
    assert client.post(API, json={}).status_code == 202
    assert client.post(API, json={}).get_json()["error"]["message"] == "Une comparaison avec Sirene est déjà en cours."


def test_cancel_between_batches(batch, monkeypatch):
    monkeypatch.setattr(sirene, "BATCH", 2)
    sirene_refresh.cancel(77)
    result = sirene_refresh.run(None, 77, None)
    assert result["cancelled"] is True and result["items"] == [] and result["total"] == 4
    assert not sirene_refresh._is_cancelled(77)


def test_not_configured(login_as, app):
    assert login_as().post(API, json={}).status_code == 503
