"""Lot AG9a.d : résumé du lundi de l'échéancier (US-A2 au 02/11/2026).

Service des quatre blocs, notification de la semaine, e-mail aux abonnés par la commande `flask agenda
send-weekly` (idempotent), désabonnement par le lien de l'e-mail ou depuis l'échéancier.
"""
from datetime import date

import pytest

from app.extensions import db
from app.models import AgendaSubscription, Instance, InstanceMembership, Notification, User
from app.services import agenda_summary
from test_agenda import MONDAY, farm  # noqa: F401


@pytest.fixture()
def mail(app):
    app.config["APP_BASE_URL"] = "https://lyvre.example"
    sent = []
    return sent, lambda to, subject, text: sent.append((to, subject, text))


def _user(email, role=None, is_admin=False):
    user = User(email=email, is_admin=is_admin)
    user.set_password("x")
    db.session.add(user)
    db.session.flush()
    if role:
        db.session.add(InstanceMembership(user_id=user.id, instance_id=Instance.query.one().id, role=role))
    db.session.commit()
    return user


def test_weekly_summary_blocks(farm):
    summary = agenda_summary.weekly_summary(MONDAY)
    assert summary["week"] == "2026-W45" and summary["monday"] == "2026-11-02"
    (installment,) = [r for r in summary["this_week"] if r["title"].startswith("Acomptes")]
    assert installment["amount_cents"] == 100100 and installment["date"] == "2026-11-05"
    assert "montant calculé par Lyvre, à valider" in installment["missing"]
    assert installment["action_label"] == "Préparer le 3525 bis"
    late = [r for r in summary["late"] if r["label"] == "Taxe foncière non bâtie"]
    assert late and summary["counts"]["late"] == len(summary["late"]) and not summary["empty"]


def test_send_weekly_once_per_week(farm, mail):
    sent, deliver = mail
    _user("expert@example.org", role="accountant")              # lecture seule : jamais destinataire
    _user("ops@example.org", is_admin=True)                     # administrateur global sans rôle : pas abonné
    logs = []
    stats = agenda_summary.send_weekly(MONDAY, deliver=deliver, log=logs.append)
    assert stats == {"instances": 1, "sent": 1, "skipped": 0, "failed": 0, "notifications": 1}
    ((to, subject, text),) = sent
    assert to == "user@example.org" and "semaine du 02/11" in subject
    assert "Acompte de TVA" in text and "1 001,00 € calculés par Lyvre" in text
    assert "https://lyvre.example/agenda/unsubscribe?token=" in text and "Pénalités" in text
    note = Notification.query.filter_by(kind="agenda_weekly").one()
    assert note.user_id is None and note.url == "/agenda/" and "cette semaine" in note.message
    again = agenda_summary.send_weekly(date(2026, 11, 4), deliver=deliver, log=logs.append)
    assert again["sent"] == 0 and again["skipped"] == 1 and again["notifications"] == 0 and len(sent) == 1
    assert any("user=" in line and "envoyé" in line for line in logs)
    next_week = agenda_summary.send_weekly(date(2026, 11, 9), deliver=deliver, log=logs.append)
    assert next_week["sent"] == 1 and AgendaSubscription.query.one().last_sent_week == "2026-W46"


def test_failures_are_counted_and_retried(farm, mail):
    def broken(*_):
        raise OSError("SMTP indisponible")
    stats = agenda_summary.send_weekly(MONDAY, deliver=broken, log=lambda _: None)
    assert stats["failed"] == 1 and AgendaSubscription.query.count() == 0
    sent, deliver = mail
    assert agenda_summary.send_weekly(MONDAY, deliver=deliver, log=lambda _: None)["sent"] == 1


def test_global_admin_can_opt_in(farm, mail):
    sent, deliver = mail
    ops = _user("ops@example.org", is_admin=True)
    agenda_summary.set_subscribed(ops.id, True)
    db.session.commit()
    assert [u.email for u in agenda_summary.recipients(Instance.query.one())] == ["user@example.org", "ops@example.org"]


def test_unsubscribe_link(farm, mail):
    client = farm["client"]
    sent, deliver = mail
    agenda_summary.send_weekly(MONDAY, deliver=deliver, log=lambda _: None)
    link = sent[0][2].split("https://lyvre.example")[-1].split()[0]
    page = client.get(link)
    assert page.status_code == 200 and "Me désabonner" in page.get_data(as_text=True)
    assert AgendaSubscription.query.one().subscribed is True                  # la prévisualisation ne désabonne pas
    token = link.split("token=")[1]
    done = client.post("/agenda/unsubscribe", data={"token": token})
    assert done.status_code == 200 and "ne recevrez plus" in done.get_data(as_text=True)
    assert AgendaSubscription.query.one().subscribed is False
    assert agenda_summary.recipients(Instance.query.one()) == []
    assert client.get("/agenda/unsubscribe?token=faux").status_code == 404


def test_summary_and_subscription_api(farm):
    client = farm["client"]
    body = client.get("/api/v1/agenda/summary").get_json()["item"]
    assert set(body["counts"]) == {"late", "this_week", "to_prepare", "to_check"}
    sub = client.get("/api/v1/agenda/subscription").get_json()["item"]
    assert sub == {"subscribed": True, "email": "user@example.org", "available": True, "last_sent_week": None}
    resp = client.put("/api/v1/agenda/subscription", json={"subscribed": False})
    assert resp.status_code == 200 and resp.get_json()["item"]["subscribed"] is False
    assert client.put("/api/v1/agenda/subscription", json={"subscribed": "non"}).status_code == 422


def test_cli_dry_run(farm, app):
    result = app.test_cli_runner().invoke(args=["agenda", "send-weekly", "--date", "2026-11-02", "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "essai (non envoyé)" in result.output and "1 exploitation(s), 1 envoi(s)" in result.output
    assert Notification.query.count() == 0 and AgendaSubscription.query.count() == 0
    bad = app.test_cli_runner().invoke(args=["agenda", "send-weekly", "--date", "02/11/2026"])
    assert bad.exit_code != 0


def test_weekly_mail_on_fixture_farm_a(app, login_as, mail):
    """Recette du design (§ 10) : exploitation fictive A (EARL, clôture au 31/01) au lundi 02/11/2026."""
    from scripts.agri_fixtures.load import FIXTURES, load
    from test_agri_fixtures import _agri_instance

    login_as(role="treasurer")
    _agri_instance()
    load(FIXTURES / "A_earl_porcs_rs")
    agenda_summary.weekly_summary(MONDAY)          # pas d'erreur sur des données réelles anonymisées
    sent, deliver = mail
    stats = agenda_summary.send_weekly(MONDAY, deliver=deliver, log=lambda _: None)
    assert stats["failed"] == 0 and stats["sent"] == 1, stats
    subject, text = sent[0][1], sent[0][2]
    assert subject.startswith("Lyvre — EARL des Pins (fictive) : échéancier de la semaine du 02/11")
    assert "En retard (2)" in text and "15/10 · Taxe foncière non bâtie (SIP, 2026)" in text
    assert "10/12 · Appel de cotisations MSA" in text and "À faire : date à confirmer" in text
