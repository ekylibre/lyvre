"""Lot AG9a.e : export iCal de l'échéancier (RFC 5545), URL secrète par utilisateur et par instance."""
import re
from datetime import date, datetime, timezone

from app.extensions import db
from app.models import InstanceMembership, User
from app.services import agenda_ical
from test_agenda import MONDAY, farm  # noqa: F401


def _unfold(body: str) -> list[str]:
    assert body.endswith("\r\n") and "\n" not in body.replace("\r\n", "")       # CRLF partout
    for raw in body.split("\r\n")[:-1]:
        assert len(raw.encode("utf-8")) <= 75, raw                              # lignes pliées à 75 octets
    return body.replace("\r\n ", "").split("\r\n")[:-1]


def _validate(body: str) -> list[dict]:
    """Contrôles RFC 5545 : imbrication des composants, propriétés obligatoires, dates, UID uniques."""
    lines = _unfold(body)
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-1] == "END:VCALENDAR"
    stack, events, current = [], [], None
    for line in lines:
        name, sep, value = line.partition(":")
        assert sep and re.fullmatch(r"[A-Z-]+(;[A-Z-]+=[^;:]+)*", name), line
        if name == "BEGIN":
            stack.append(value)
            if value == "VEVENT":
                current = {}
        elif name == "END":
            assert stack.pop() == value
            if value == "VEVENT":
                events.append(current)
                current = None
        elif current is not None and stack[-1] == "VEVENT":
            current[name.split(";")[0]] = value
    assert not stack
    header = {line.split(":")[0] for line in lines[1:8]}
    assert {"VERSION", "PRODID"} <= header
    for event in events:
        assert {"UID", "DTSTAMP", "DTSTART", "SUMMARY"} <= set(event), event
        assert re.fullmatch(r"\d{8}", event["DTSTART"]) and re.fullmatch(r"\d{8}T\d{6}Z", event["DTSTAMP"])
    assert len({e["UID"] for e in events}) == len(events)
    return events


def test_escape_and_fold():
    assert agenda_ical.escape("a;b,c\\d\ne") == "a\\;b\\,c\\\\d\\ne"
    folded = agenda_ical.fold("DESCRIPTION:" + "é" * 80)
    parts = folded.split("\r\n")
    assert all(len(p.encode()) <= 75 for p in parts) and all(p.startswith(" ") for p in parts[1:])
    assert folded.replace("\r\n ", "") == "DESCRIPTION:" + "é" * 80


def test_calendar_is_valid(farm, app):
    app.config["APP_BASE_URL"] = "https://lyvre.example"
    body = agenda_ical.calendar("EARL fictive", "test", "https://lyvre.example", MONDAY,
                                datetime(2026, 11, 2, 7, 0, tzinfo=timezone.utc))
    events = _validate(body)
    (installment,) = [e for e in events if e["SUMMARY"].startswith("Acompte de TVA") and e["DTSTART"] == "20261105"]
    assert installment["DTEND"] == "20261106" and installment["URL"] == "https://lyvre.example/vat-returns/"
    assert "1 001\\,00 €" in installment["DESCRIPTION"]
    assert min(e["DTSTART"] for e in events) >= "20261003"                    # J-30
    again = agenda_ical.calendar("EARL fictive", "test", "https://lyvre.example", MONDAY)
    assert {e["UID"] for e in _validate(again)} == {e["UID"] for e in events}   # UID stables


def test_secret_url_lifecycle(farm, app):
    client = farm["client"]
    assert client.get("/api/v1/agenda/ical").get_json()["item"]["url"] is None
    url = client.post("/api/v1/agenda/ical").get_json()["item"]["url"]
    path = url[url.index("/agenda/ical/"):]
    assert re.fullmatch(r"/agenda/ical/test/[A-Za-z0-9_-]{40,}\.ics", path)
    resp = client.get(path)
    assert resp.status_code == 200 and resp.headers["Content-Type"] == "text/calendar; charset=utf-8"
    _validate(resp.get_data(as_text=True))
    assert client.get(path.replace("/test/", "/autre/")).status_code == 404
    new = client.post("/api/v1/agenda/ical").get_json()["item"]["url"]
    assert new != url and client.get(path).status_code == 404                 # régénérée : l'ancienne ne marche plus
    path = new[new.index("/agenda/ical/"):]
    InstanceMembership.query.delete()                                         # accès retiré
    db.session.commit()
    assert client.get(path).status_code == 404


def test_revoke(farm):
    client = farm["client"]
    url = client.post("/api/v1/agenda/ical").get_json()["item"]["url"]
    path = url[url.index("/agenda/ical/"):]
    assert client.delete("/api/v1/agenda/ical").get_json()["item"]["url"] is None
    assert client.get(path).status_code == 404
    assert agenda_ical.owner_of("") is None and agenda_ical.owner_of("x" * 43) is None
    assert User.query.count() == 1
