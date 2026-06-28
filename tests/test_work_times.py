"""Tests du module Temps de travaux : modèle, bulk bénévole, import, CRUD types."""
import io
from datetime import date

import pytest

from app.extensions import db
from app.models import Entity, TaskType, WorkTime


@pytest.fixture()
def client(app):
    # Pas d'authentification réelle en test : on bypass @login_required.
    app.config["LOGIN_DISABLED"] = True
    return app.test_client()


# --- modèle : valuation_cents --------------------------------------------


def test_valuation_rounding(session):
    tt = TaskType(name="Caisse", hourly_rate_cents=2500)
    ent = Entity(name="Bob", is_benevole=True)
    db.session.add_all([tt, ent])
    db.session.commit()
    wt = WorkTime(entity_id=ent.id, task_type_id=tt.id,
                  work_date=date(2026, 6, 1), hours=2.5)
    db.session.add(wt)
    db.session.commit()
    # 2.5 h × 25,00 €/h = 62,50 € = 6250 centimes
    assert wt.valuation_cents == 6250


def test_valuation_rounds_to_nearest_cent(session):
    tt = TaskType(name="Tri", hourly_rate_cents=3333)  # 33,33 €/h
    ent = Entity(name="Alice", is_benevole=True)
    db.session.add_all([tt, ent])
    db.session.commit()
    wt = WorkTime(entity_id=ent.id, task_type_id=tt.id,
                  work_date=date(2026, 6, 1), hours=1.5)
    db.session.add(wt)
    db.session.commit()
    # 1.5 × 3333 = 4999.5 -> arrondi 5000
    assert wt.valuation_cents == 5000


def test_valuation_zero_rate(session):
    tt = TaskType(name="Bénévolat pur", hourly_rate_cents=0)
    ent = Entity(name="Carol", is_benevole=True)
    db.session.add_all([tt, ent])
    db.session.commit()
    wt = WorkTime(entity_id=ent.id, task_type_id=tt.id,
                  work_date=date(2026, 6, 1), hours=10)
    db.session.add(wt)
    db.session.commit()
    assert wt.valuation_cents == 0


# --- bulk bénévole --------------------------------------------------------


def test_bulk_benevole_set_and_unset(client, session):
    a = Entity(name="A", entity_type="ADHERENT")
    b = Entity(name="B", entity_type="ADHERENT")
    c = Entity(name="C", entity_type="ADHERENT")
    db.session.add_all([a, b, c])
    db.session.commit()

    resp = client.post("/entities/members/bulk-benevole", data={
        "action": "set", "selected": [str(a.id), str(b.id)],
    }, follow_redirects=False)
    assert resp.status_code == 302
    assert Entity.query.get(a.id).is_benevole is True
    assert Entity.query.get(b.id).is_benevole is True
    assert Entity.query.get(c.id).is_benevole is False

    resp = client.post("/entities/members/bulk-benevole", data={
        "action": "unset", "selected": [str(a.id)],
    })
    assert resp.status_code == 302
    assert Entity.query.get(a.id).is_benevole is False
    assert Entity.query.get(b.id).is_benevole is True


def test_bulk_benevole_no_selection(client, session):
    resp = client.post("/entities/members/bulk-benevole",
                       data={"action": "set"}, follow_redirects=True)
    assert resp.status_code == 200
    assert "Aucun adhérent sélectionné".encode() in resp.data


# --- import ---------------------------------------------------------------


def _csv_bytes(rows):
    # encode utf-8-sig écrit le BOM ; ne pas l'ajouter une 2e fois en littéral.
    header = "Bénévole;Type de tâche;Date;Heures;Notes\n"
    return (header + "".join(rows)).encode("utf-8-sig")


def test_import_valid_and_errors(session):
    from app.services.work_time_import import import_work_times

    ent = Entity(name="Jean Bénévole", email="jean@asso.fr", is_benevole=True)
    tt = TaskType(name="Tenue de la caisse", hourly_rate_cents=2500)
    db.session.add_all([ent, tt])
    db.session.commit()

    rows = [
        "Jean Bénévole;Tenue de la caisse;01/06/2026;2,5;RAS\n",          # ok, virgule
        "jean@asso.fr;Tenue de la caisse;2026-06-02;3.0;par email\n",     # ok, email + point + iso date
        "Inconnu;Tenue de la caisse;03/06/2026;1;\n",                      # bénévole introuvable
        "Jean Bénévole;Type fantôme;03/06/2026;1;\n",                      # type inconnu
        "Jean Bénévole;Tenue de la caisse;32/13/2026;1;\n",               # date invalide
        "Jean Bénévole;Tenue de la caisse;04/06/2026;zéro;\n",            # heures invalides
        ";;;;\n",                                                          # ligne vide -> skipped
    ]
    result = import_work_times(io.BytesIO(_csv_bytes(rows)), "temps.csv")

    assert result["imported"] == 2
    assert result["skipped"] == 1
    assert len(result["errors"]) == 4

    saved = WorkTime.query.order_by(WorkTime.work_date).all()
    assert len(saved) == 2
    assert float(saved[0].hours) == 2.5
    assert saved[0].valuation_cents == 6250  # 2.5 × 2500


# --- types de tâches : suppression refusée si utilisé ---------------------


def test_delete_task_type_in_use_refused(client, session):
    ent = Entity(name="X", is_benevole=True)
    tt = TaskType(name="Utilisé", hourly_rate_cents=1000)
    db.session.add_all([ent, tt])
    db.session.commit()
    db.session.add(WorkTime(entity_id=ent.id, task_type_id=tt.id,
                            work_date=date(2026, 6, 1), hours=1))
    db.session.commit()

    resp = client.post(f"/work-times/task-types/{tt.id}/delete",
                       follow_redirects=True)
    assert resp.status_code == 200
    assert "Impossible de supprimer".encode() in resp.data
    assert TaskType.query.get(tt.id) is not None  # toujours là


def test_delete_unused_task_type_ok(client, session):
    tt = TaskType(name="Libre", hourly_rate_cents=0)
    db.session.add(tt)
    db.session.commit()
    tid = tt.id
    resp = client.post(f"/work-times/task-types/{tid}/delete",
                       follow_redirects=True)
    assert resp.status_code == 200
    assert TaskType.query.get(tid) is None


# --- rate parsing (euros -> centimes) -------------------------------------


def test_task_type_create_rate_conversion(client, session):
    resp = client.post("/work-times/task-types/new", data={
        "name": "Compta", "hourly_rate": "25,50", "is_active": "1",
    }, follow_redirects=True)
    assert resp.status_code == 200
    tt = TaskType.query.filter_by(name="Compta").first()
    assert tt is not None
    assert tt.hourly_rate_cents == 2550
