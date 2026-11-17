"""Formulaire de contact de lyvre.org : validation, robots, débit, envoi Brevo (simulé)."""
import sys
import time
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).parent))
import contact  # noqa: E402


class FakeBrevo:
    def __init__(self, status=201, fail=False):
        self.calls, self.status, self.fail = [], status, fail

    def post(self, path, payload):
        if self.fail:
            raise requests.ConnectionError("hors ligne")
        self.calls.append((path, payload))
        return type("R", (), {"status_code": self.status})()


def form(**overrides):
    data = {"name": "Camille Martin", "email": "camille@example.org", "profile": "asso",
            "message": "Bonjour, je voudrais installer Lyvre.", "consent": "on",
            "started_at": str(int(time.time() * 1000) - 10_000)}
    data.update(overrides)
    return {k: v for k, v in data.items() if v is not None}


@pytest.fixture
def setup():
    brevo = FakeBrevo()
    app = contact.create_app({"CONTACT_TO": "equipe@example.org", "CONTACT_FROM": "site@example.org",
                              "BREVO_CONTACT_LIST_ID": "7"}, brevo=brevo)
    return app.test_client(), brevo


def post(client, data, ip="203.0.113.5"):
    return client.post("/api/contact", data=data, headers={"X-Forwarded-For": f"{ip}, 10.0.0.2"})


def test_valid_message_is_sent_with_reply_to_and_added_to_the_list(setup):
    client, brevo = setup
    res = post(client, form())
    assert res.status_code == 303 and res.headers["Location"] == "/contact/merci/"
    (path, mail), (path2, added) = brevo.calls
    assert path == "/smtp/email" and mail["to"] == [{"email": "equipe@example.org"}]
    assert mail["replyTo"] == {"email": "camille@example.org", "name": "Camille Martin"}
    assert "Association" in mail["subject"] and "installer Lyvre" in mail["textContent"]
    assert path2 == "/contacts" and added == {"email": "camille@example.org", "listIds": [7], "updateEnabled": True}


@pytest.mark.parametrize("change", [
    {"email": "pas-une-adresse"}, {"name": ""}, {"profile": "pirate"}, {"message": "court"},
    {"consent": None}, {"message": "x" * 5001},
])
def test_invalid_fields_are_refused(setup, change):
    client, brevo = setup
    res = post(client, form(**change))
    assert res.status_code == 303 and "erreur=champs" in res.headers["Location"]
    assert brevo.calls == []


def test_honeypot_and_too_fast_are_silently_ignored(setup):
    client, brevo = setup
    assert post(client, form(website="http://spam.example")).headers["Location"] == "/contact/merci/"
    assert post(client, form(started_at=str(int(time.time() * 1000)))).headers["Location"] == "/contact/merci/"
    assert brevo.calls == []


def test_without_javascript_the_delay_is_not_required(setup):
    client, brevo = setup
    assert post(client, form(started_at=None)).headers["Location"] == "/contact/merci/"
    assert len(brevo.calls) == 2


def test_rate_limited_per_visitor_ip(setup):
    client, brevo = setup
    codes = [post(client, form()).headers["Location"] for _ in range(6)]
    assert codes[:5] == ["/contact/merci/"] * 5 and "erreur=trop" in codes[5]
    assert post(client, form(), ip="198.51.100.9").headers["Location"] == "/contact/merci/"


def test_rate_window_slides():
    now = [0.0]
    limiter = contact.RateLimiter(per_ip=(2, 60), overall=(100, 3600), clock=lambda: now[0])
    assert limiter.allow("a") and limiter.allow("a") and not limiter.allow("a")
    now[0] = 61
    assert limiter.allow("a")


@pytest.mark.parametrize("brevo", [FakeBrevo(status=401), FakeBrevo(fail=True), None])
def test_brevo_failure_or_missing_key(brevo):
    app = contact.create_app({"BREVO_API_KEY": ""}, brevo=brevo)
    res = post(app.test_client(), form())
    assert "erreur=service" in res.headers["Location"]


def test_oversized_body_is_refused(setup):
    client, brevo = setup
    res = post(client, form(message="x" * 40_000))
    assert res.status_code == 303 and "erreur=champs" in res.headers["Location"]
