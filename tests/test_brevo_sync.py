"""Lot B2 : synchronisation des adhérents vers une liste Brevo, contre un faux Brevo en mémoire qui
reproduit l'unicité de l'e-mail et la réinscription d'un désinscrit dont on change l'e-mail.
Critères : rattachement des contacts existants sans doublon, aperçu sans écriture, second passage
sans écriture, changement d'e-mail, désinscrits jamais réinscrits, conflits, sorties de la liste."""
from datetime import datetime

import pytest

from app.extensions import db
from app.models import Entity, HelloAssoItem, HelloAssoOrder
from app.models.brevo_link import BrevoLink
from app.services import brevo_client, brevo_sync, external_config

LIST = 12
ALL_ATTRIBUTES = ["PRENOM", "NOM", "DATE_ADH", "LYVRE_STATUT", "LYVRE_ECHEANCE", "LYVRE_BENEVOLE", "EXT_ID"]


class FakeBrevo:
    def __init__(self, attributes=ALL_ATTRIBUTES):
        self.contacts_by_id, self.next_id, self.writes = {}, 100, []
        self.attribute_names = attributes
        self.fail_batch = False

    def add(self, email, lists=(), blacklisted=False, **attributes):
        self.next_id += 1
        self.contacts_by_id[self.next_id] = {"id": self.next_id, "email": email, "emailBlacklisted": blacklisted,
                                             "listIds": list(lists), "attributes": dict(attributes)}
        return self.next_id

    def by_email(self, email):
        return next((c for c in self.contacts_by_id.values() if c["email"] == email), None)

    # API du client
    def attributes(self):
        return [{"name": n, "category": "normal"} for n in self.attribute_names]

    def contacts(self):
        return [dict(c, attributes=dict(c["attributes"]), listIds=list(c["listIds"])) for c in self.contacts_by_id.values()]

    def create_contact(self, email, ext_id, attributes, list_ids):
        self.writes.append(("create", email))
        if self.by_email(email):
            raise brevo_client.BrevoError("duplicate", "Ce contact existe déjà dans Brevo.")
        cid = self.add(email, list_ids, **attributes)
        self.contacts_by_id[cid]["attributes"]["EXT_ID"] = ext_id
        return cid

    def _apply(self, cid, row):
        contact = self.contacts_by_id[cid]
        attrs = dict(row.get("attributes") or {})
        if "EMAIL" in attrs:
            email = attrs.pop("EMAIL")
            if self.by_email(email) and self.by_email(email)["id"] != cid:
                raise brevo_client.BrevoError("invalid", "duplicate_parameter")
            contact["email"] = email
            contact["emailBlacklisted"] = False  # comportement documenté de Brevo
        contact["attributes"].update({k: v for k, v in attrs.items() if k in self.attribute_names})
        if row.get("ext_id"):
            contact["attributes"]["EXT_ID"] = row["ext_id"]
        contact["listIds"] = sorted(set(contact["listIds"]) | set(row.get("listIds") or []))
        assert "emailBlacklisted" not in row and "forceMerge" not in row

    def update_batch(self, rows):
        self.writes.append(("batch", len(rows)))
        if self.fail_batch:
            raise brevo_client.BrevoError("invalid", "Brevo a refusé la demande.")
        for row in rows:
            self._apply(row["id"], row)

    def update_contact(self, cid, row):
        self.writes.append(("update", cid))
        if self.contacts_by_id[cid]["email"] == "refuse@example.org":
            raise brevo_client.BrevoError("invalid", "Brevo a refusé la demande : invalid_parameter")
        self._apply(cid, row)

    def unlink(self, list_id, ids):
        self.writes.append(("unlink", tuple(ids)))
        for cid in ids:
            self.contacts_by_id[cid]["listIds"] = [l for l in self.contacts_by_id[cid]["listIds"] if l != list_id]


@pytest.fixture()
def brevo(instance, monkeypatch):
    fake = FakeBrevo()
    monkeypatch.setattr(brevo_client.Client, "from_config", classmethod(lambda cls, timeout=15: fake))
    external_config.set_many("brevo", {"api_key": "xkeysib-test", "list_id": str(LIST)})
    external_config.set_enabled("brevo", True)
    return fake


def _member(name, email, first=None, last=None, benevole=False, joined=datetime(2026, 2, 1)):
    entity = Entity(name=name, entity_type="ADHERENT", email=email, is_member=True, is_benevole=benevole)
    db.session.add(entity)
    db.session.flush()
    order = HelloAssoOrder(helloasso_id=entity.id * 10, entity_id=entity.id, date=joined, amount_total_cents=2000,
                           form_slug="adhesion", form_type="Membership", payer_first_name=first, payer_last_name=last)
    db.session.add(order)
    db.session.flush()
    db.session.add(HelloAssoItem(helloasso_id=entity.id * 10 + 1, order_id=order.id, entity_id=entity.id,
                                 type="Membership", name="Adhésion", amount_cents=2000,
                                 user_first_name=first, user_last_name=last))
    db.session.commit()
    return entity


@pytest.fixture()
def people(brevo):
    """Compte Brevo qui contient déjà deux adhérents (l'un désinscrit) ; un adhérent nouveau ; un sans e-mail."""
    brevo.add("anne@example.org", lists=[10], PRENOM="Anne", DATE_ADH="2025-06-20")
    brevo.add("bruno@example.org", lists=[10], blacklisted=True)
    brevo.add("ancien@example.org", lists=[LIST])  # ancien contact de la liste, inconnu de Lyvre
    return {"anne": _member("Anne Martin", "anne@example.org", "Anne-Marie", "Martin", benevole=True),
            "bruno": _member("Bruno Petit", "Bruno@Example.org "),
            "chloe": _member("Chloé Durand", "chloe@example.org", "Chloé", "Durand"),
            "sans": _member("Sans E-mail", None)}


def test_preview_writes_nothing(people, brevo):
    report = brevo_sync.run(dry_run=True)
    assert (report["created"], report["linked"], report["updated"], report["conflicts"], report["skipped"],
            report["blacklisted"], report["orphans"]) == (1, 2, 0, 0, 1, 1, 1)
    assert brevo.writes == [] and BrevoLink.query.count() == 0
    assert report["skipped_items"][0]["name"] == "Sans E-mail"


def test_first_sync_links_existing_contacts_without_duplicates(people, brevo):
    assert brevo_sync.first_sync_pending()
    report = brevo_sync.run(dry_run=False)
    assert (report["created"], report["linked"], report["errors"]) == (1, 2, [])
    assert [w for w in brevo.writes if w[0] == "create"] == [("create", "chloe@example.org")]  # aucun doublon
    assert len(brevo.contacts_by_id) == 4
    anne = brevo.by_email("anne@example.org")
    assert LIST in anne["listIds"] and 10 in anne["listIds"]  # ajoutée à la liste, rien retiré ailleurs
    assert anne["attributes"]["PRENOM"] == "Anne"            # partagé : jamais écrasé
    assert anne["attributes"]["NOM"] == "Martin"             # partagé vide : complété
    assert anne["attributes"]["DATE_ADH"] == "2026-02-01" and anne["attributes"]["LYVRE_BENEVOLE"] is True
    assert anne["attributes"]["LYVRE_STATUT"] in ("À jour", "Expire bientôt", "Échue")
    assert anne["attributes"]["EXT_ID"] == f"lyvre-test-{people['anne'].id}"
    assert brevo.by_email("bruno@example.org")["emailBlacklisted"] is True  # resté désinscrit
    assert BrevoLink.query.count() == 3 and not brevo_sync.first_sync_pending() and brevo_sync.has_links()


def test_second_pass_writes_nothing(people, brevo):
    brevo_sync.run(dry_run=False)
    brevo.writes.clear()
    report = brevo_sync.run(dry_run=False)
    assert (report["unchanged"], report["updated"], report["created"]) == (3, 0, 0)
    assert brevo.writes == []  # aucun appel d'écriture


def test_email_change_updates_the_same_contact(people, brevo):
    brevo_sync.run(dry_run=False)
    contact_id = BrevoLink.query.filter_by(entity_id=people["chloe"].id).one().contact_id
    people["chloe"].email = "chloe.durand@example.org"
    db.session.commit()
    report = brevo_sync.run(dry_run=False)
    assert report["created"] == 0 and report["updated"] == 1
    assert brevo.contacts_by_id[contact_id]["email"] == "chloe.durand@example.org"
    assert len(brevo.contacts_by_id) == 4


def test_email_conflicts_are_reported_not_merged(people, brevo):
    brevo_sync.run(dry_run=False)
    brevo.add("pris@example.org")
    people["chloe"].email = "pris@example.org"     # déjà un autre contact Brevo
    people["bruno"].email = "bruno2@example.org"   # désinscrit : changer l'e-mail le réinscrirait
    db.session.commit()
    report = brevo_sync.run(dry_run=False)
    reasons = {c["name"]: c["reason"] for c in report["conflict_items"]}
    assert "déjà utilisé dans Brevo" in reasons["Chloé Durand"]
    assert "réinscrirait" in reasons["Bruno Petit"]
    assert brevo.by_email("bruno@example.org")["emailBlacklisted"] is True
    assert BrevoLink.query.filter_by(entity_id=people["bruno"].id).one().state == "conflict"
    assert len(brevo.contacts_by_id) == 5


def test_leaving_members_are_removed_from_the_list_not_deleted(people, brevo):
    brevo_sync.run(dry_run=False)
    chloe_contact = BrevoLink.query.filter_by(entity_id=people["chloe"].id).one().contact_id
    db.session.delete(people["chloe"])
    people["anne"].entity_type = "AUTRE"
    db.session.commit()
    report = brevo_sync.run(dry_run=False)
    assert report["unlinked"] == 2
    assert LIST not in brevo.contacts_by_id[chloe_contact]["listIds"] and chloe_contact in brevo.contacts_by_id
    assert LIST not in brevo.by_email("anne@example.org")["listIds"]
    assert brevo.by_email("ancien@example.org")["listIds"] == [LIST]  # contact inconnu : jamais retiré
    # Retour d'Anne parmi les adhérents : même contact, remis dans la liste.
    people["anne"].entity_type = "ADHERENT"
    db.session.commit()
    report = brevo_sync.run(dry_run=False)
    assert report["created"] == 0 and LIST in brevo.by_email("anne@example.org")["listIds"]


def test_subset_after_helloasso_does_not_unlink(people, brevo):
    brevo_sync.run(dry_run=False)
    db.session.delete(people["chloe"])
    db.session.commit()
    report = brevo_sync.run(dry_run=False, entity_ids=[people["anne"].id])
    assert report["unlinked"] == 0 and report["unchanged"] == 1


def test_missing_attributes_are_not_sent(people, brevo):
    brevo.attribute_names = ["PRENOM", "NOM", "EXT_ID"]
    brevo_sync.run(dry_run=False)
    assert "LYVRE_STATUT" not in brevo.by_email("chloe@example.org")["attributes"]


def test_refused_batch_is_replayed_contact_by_contact(people, brevo):
    brevo.by_email("anne@example.org")["email"] = "refuse@example.org"
    people["anne"].email = "refuse@example.org"
    db.session.commit()
    brevo.fail_batch = True
    report = brevo_sync.run(dry_run=False)
    assert report["errors"] == ["Anne Martin : Brevo a refusé la demande : invalid_parameter"]
    assert BrevoLink.query.filter_by(entity_id=people["anne"].id).first() is None  # non lié : repris au passage suivant
    assert BrevoLink.query.filter_by(entity_id=people["bruno"].id).one().state == "linked"


def test_list_must_be_chosen(people, brevo):
    external_config.set_many("brevo", {"api_key": "xkeysib-test", "list_id": ""})
    with pytest.raises(brevo_sync.SyncError):
        brevo_sync.run(dry_run=True)


def test_job_and_notification(people, brevo, monkeypatch, app):
    from app.models import Notification, SyncJob
    from app.services import sync_jobs
    from test_sync_jobs import ImmediateThread
    monkeypatch.setattr(sync_jobs.threading, "Thread", ImmediateThread)
    job = brevo_sync.start(app, dry_run=True)
    db.session.expire_all()
    job = db.session.get(SyncJob, job.id)
    assert job.status == "done" and '"dry_run": true' in job.result_json
    note = Notification.query.filter_by(job_id=job.id).one()
    assert note.url == f"/entities/members/brevo/{job.id}"
    assert note.message.startswith("Aperçu : 1 créé(s), 2 rattaché(s)") and "1 désinscrit(s)" in note.message


# ------------------------------------------------------------------ routes et enchaînement (lot B3)


@pytest.fixture()
def api_client(people, brevo, login_as, monkeypatch):
    from app.services import sync_jobs
    from test_sync_jobs import ImmediateThread
    monkeypatch.setattr(sync_jobs.threading, "Thread", ImmediateThread)
    return login_as()


def test_preview_then_sync_through_the_api(api_client, brevo):
    status = api_client.get("/api/v1/brevo/status").get_json()
    assert status["first_sync_pending"] and status["links"] == 0 and status["last_job"] is None
    refused = api_client.post("/api/v1/brevo/sync", json={"dry_run": False})
    assert refused.status_code == 422 and "aperçu" in refused.get_json()["error"]["message"]

    resp = api_client.post("/api/v1/brevo/sync", json={"dry_run": True})
    assert resp.status_code == 202, resp.get_json()
    job_id = resp.get_json()["job"]["id"]
    db.session.expire_all()
    body = api_client.get(f"/api/v1/brevo/sync/{job_id}").get_json()
    assert body["job"]["status"] == "done" and body["result"]["dry_run"] is True and body["result"]["linked"] == 2
    assert brevo.writes == [] and body["first_sync_pending"] is False  # aperçu abouti : synchronisation permise

    resp = api_client.post("/api/v1/brevo/sync", json={"dry_run": False})
    assert resp.status_code == 202, resp.get_json()
    db.session.expire_all()
    status = api_client.get("/api/v1/brevo/status").get_json()
    assert status["links"] == 3 and status["last_job"]["id"] == resp.get_json()["job"]["id"]
    assert api_client.get("/api/v1/brevo/sync/999").status_code == 404


def test_sync_guards(api_client, brevo, monkeypatch):
    assert api_client.post("/api/v1/brevo/sync", json={"dry_run": True, "entity_ids": "1"}).status_code == 422
    from app.services import sync_jobs
    monkeypatch.setattr(sync_jobs.threading, "Thread", lambda **kw: type("T", (), {"start": lambda self: None})())
    assert api_client.post("/api/v1/brevo/sync", json={"dry_run": True}).status_code == 202
    assert api_client.post("/api/v1/brevo/sync", json={"dry_run": True}).status_code == 409
    external_config.set_enabled("brevo", False)
    assert api_client.post("/api/v1/brevo/sync", json={"dry_run": True}).get_json()["error"]["code"] == \
        "integration_required"


def test_accountant_reads_but_cannot_sync(api_client):
    from app.models import InstanceMembership
    InstanceMembership.query.one().role = "accountant"
    db.session.commit()
    assert api_client.get("/api/v1/brevo/status").status_code == 200
    assert api_client.post("/api/v1/brevo/sync", json={"dry_run": True}).status_code == 403


def test_helloasso_sync_chains_touched_members_once_linked(api_client, brevo, people, monkeypatch):
    from app.api import entities as entities_api
    started = []
    monkeypatch.setattr(brevo_sync, "start", lambda app, dry_run, entity_ids=None: started.append((dry_run, entity_ids)))
    result = {k: 0 for k in ("orders_imported", "orders_updated", "items_imported", "items_updated", "payments_imported",
                             "payments_updated", "members_created", "members_flagged")}
    monkeypatch.setattr(entities_api, "sync_helloasso", lambda: {**result, "member_ids": [people["anne"].id]})
    api_client.post("/api/v1/helloasso/sync")
    assert started == []  # aucune synchronisation Brevo encore : rien n'est envoyé
    db.session.add(BrevoLink(entity_id=people["anne"].id, contact_id=1))
    db.session.commit()
    resp = api_client.post("/api/v1/helloasso/sync")
    assert started == [(False, [people["anne"].id])]
    assert "1 adhérent(s) envoyé(s) vers Brevo" in str(resp.get_json()["notices"])
