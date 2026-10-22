"""Tests du service de relance email des adhérents (SMTP per-tenant)."""
from datetime import date

from app.services import membership_reminders as mr
from app.models.email_template import EmailTemplate, MEMBERSHIP_REMINDER_KEY


class FakeSMTP:
    """Faux serveur SMTP capturant les messages, sans réseau."""

    def __init__(self):
        self.sent = []
        self.quit_called = False

    def send_message(self, msg):
        self.sent.append(msg)

    def noop(self):
        return (250, b"OK")

    def quit(self):
        self.quit_called = True


def _row(name, color, email="x@y.fr", status="ok", birthday=date(2026, 1, 1)):
    return {
        "name": name, "email": email, "color": color, "status": status,
        "birthday": birthday, "label": status,
    }


def test_members_to_remind_keeps_only_red_with_email_and_known_status():
    rows = [
        _row("Rouge", "red"),
        _row("Vert", "green"),
        _row("Orange", "orange"),
        _row("SansEmail", "red", email=None),
        _row("Inconnu", "red", status="?"),
    ]
    names = [r["name"] for r in mr.members_to_remind(rows)]
    assert names == ["Rouge"]


def test_smtp_configured_from_env_fallback(app):
    # conftest fixe MAIL_SERVER + MAIL_DEFAULT_SENDER -> repli .env actif.
    assert mr.smtp_configured() is True


def test_smtp_settings_reads_config(app):
    s = mr.smtp_settings()
    assert s["host"] == "smtp.example.org"
    assert s["sender"] == "noreply@example.org"
    assert s["port"] == 587
    assert s["use_tls"] is True


def test_helloasso_renewal_url_uses_config_slug(app):
    url = mr.helloasso_renewal_url()
    assert url == "https://www.helloasso.com/associations/test-org/adhesions/adhesion"


def test_render_reminder_substitutes_variables(app):
    tpl = EmailTemplate(
        key="x",
        subject="Bonjour {{ nom }}",
        body_html='<a href="{{ lien_helloasso }}">{{ date_anniversaire }}</a>',
    )
    row = _row("Durand", "red", birthday=date(2026, 3, 15))
    subject, body = mr.render_reminder(tpl, row, "https://he.llo/asso")
    assert subject == "Bonjour Durand"
    assert "15/03/2026" in body
    assert 'href="https://he.llo/asso"' in body


def test_send_reminders_sends_to_each_target(app, monkeypatch):
    fake = FakeSMTP()
    monkeypatch.setattr(mr, "_open_smtp", lambda settings, **kw: fake)
    rows = [
        _row("A", "red", email="a@x.fr"),
        _row("B", "red", email="b@x.fr"),
        _row("Vert", "green", email="c@x.fr"),  # ignoré
    ]
    result = mr.send_reminders(rows)
    assert result["sent"] == 2
    assert result["errors"] == 0
    assert fake.quit_called is True
    recipients = sorted(m["To"] for m in fake.sent)
    assert recipients == ["a@x.fr", "b@x.fr"]
    # Expéditeur appliqué depuis la config
    assert fake.sent[0]["From"] == "noreply@example.org"


def test_send_reminders_dry_run_sends_nothing(app, monkeypatch):
    monkeypatch.setattr(mr, "_open_smtp", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("ne doit pas ouvrir de connexion")))
    rows = [_row("A", "red", email="a@x.fr")]
    result = mr.send_reminders(rows, dry_run=True)
    assert result["sent"] == 0
    assert len(result["targets"]) == 1


def test_send_reminders_isolates_per_recipient_error(app, monkeypatch):
    class FlakySMTP(FakeSMTP):
        def send_message(self, msg):
            if msg["To"] == "bad@x.fr":
                raise OSError("rejeté")
            super().send_message(msg)

    fake = FlakySMTP()
    monkeypatch.setattr(mr, "_open_smtp", lambda settings, **kw: fake)
    rows = [_row("Bon", "red", email="ok@x.fr"), _row("Mauvais", "red", email="bad@x.fr")]
    result = mr.send_reminders(rows)
    assert result["sent"] == 1
    assert result["errors"] == 1
    assert "Mauvais" in result["error_lines"][0]


def test_get_or_default_returns_seed_when_absent(app):
    tpl = EmailTemplate.get_or_default(MEMBERSHIP_REMINDER_KEY)
    assert tpl.subject  # gabarit par défaut non vide
    assert "{{ lien_helloasso }}" in tpl.body_html
