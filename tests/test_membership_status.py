"""Tests unitaires des calculs de statut d'adhésion (fonctions pures)."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from app.services.membership_status import (
    member_birthday, member_status, build_member_rows, sort_member_rows,
    MEMBERSHIP_DAYS, EXPIRING_SOON_DAYS,
)

TODAY = date(2026, 6, 25)


# --- member_birthday : les 4 combinaisons HA / POS ---------------------------

def test_birthday_no_adhesion_is_today():
    assert member_birthday(None, None, TODAY) == TODAY


def test_birthday_pos_only():
    pos = datetime(2025, 1, 10)
    assert member_birthday(None, pos, TODAY) == date(2025, 1, 10) + timedelta(days=MEMBERSHIP_DAYS)


def test_birthday_ha_only():
    ha = datetime(2025, 3, 1)
    assert member_birthday(ha, None, TODAY) == date(2025, 3, 1) + timedelta(days=MEMBERSHIP_DAYS)


def test_birthday_both_uses_most_recent():
    ha = datetime(2025, 1, 1)
    pos = datetime(2025, 6, 1)  # plus récente
    assert member_birthday(ha, pos, TODAY) == date(2025, 6, 1) + timedelta(days=MEMBERSHIP_DAYS)


def test_birthday_accepts_date_and_datetime():
    assert member_birthday(date(2025, 1, 1), None, TODAY) == date(2026, 1, 1)


# --- member_status : statut (présence) ---------------------------------------

def test_status_unknown_when_no_data():
    assert member_status(None, None, TODAY)["status"] == "?"


def test_status_asha_when_pos_only():
    assert member_status(None, datetime(2026, 6, 1), TODAY)["status"] == "asha"


def test_status_ok_when_ha_present():
    assert member_status(datetime(2026, 6, 1), None, TODAY)["status"] == "ok"


# --- member_status : couleur (échéance) --------------------------------------

def test_color_red_when_no_data():
    # birthday == today -> rouge
    assert member_status(None, None, TODAY)["color"] == "red"


def test_color_green_far_future():
    # échéance largement future
    assert member_status(datetime(2026, 6, 1), None, TODAY)["color"] == "green"


def test_color_boundaries():
    # b = today -> red
    ha_red = datetime(2025, 6, 25)  # +365 = 2026-06-25 == today
    assert member_status(ha_red, None, TODAY)["color"] == "red"
    # today < b <= today+30 -> orange (échéance = today + 30)
    ha_orange = datetime(2025, 7, 25)  # +365 = 2026-07-25 = today + 30j
    assert member_status(ha_orange, None, TODAY)["color"] == "orange"
    # b = today + 31 -> green
    ha_green = datetime(2025, 7, 26)
    assert member_status(ha_green, None, TODAY)["color"] == "green"


def test_status_includes_css_and_label():
    s = member_status(None, None, TODAY)
    assert s["css"] == "bg-danger"
    assert s["label"] == s["status"]


# --- build_member_rows / sort_member_rows ------------------------------------

def _entity(eid, name, **kw):
    return SimpleNamespace(
        id=eid, name=name,
        email=kw.get("email"), is_member=kw.get("is_member", False),
        is_benevole=kw.get("is_benevole", False),
        notes=kw.get("notes"),
    )


def test_build_member_rows_shape():
    e = _entity(1, "Dupont", email="a@b.fr", is_member=True)
    rows = build_member_rows([e], {1: datetime(2026, 6, 1)}, {}, TODAY)
    assert len(rows) == 1
    r = rows[0]
    assert r["name"] == "Dupont"
    assert r["last_ha"] == datetime(2026, 6, 1)
    assert r["birthday"] == date(2026, 6, 1) + timedelta(days=MEMBERSHIP_DAYS)
    assert r["color"] == "green"
    assert r["entity"] is e


def _rows():
    e1 = _entity(1, "Bernard")
    e2 = _entity(2, "Alpha")
    e3 = _entity(3, "Zoe")
    # e1 expiré (rouge), e2 vert, e3 orange
    last_ha = {
        1: datetime(2024, 1, 1),    # très ancien -> rouge
        2: datetime(2026, 6, 1),    # récent -> vert
        3: datetime(2025, 7, 10),   # +365 = 2026-07-10 -> orange
    }
    return build_member_rows([e1, e2, e3], last_ha, {}, TODAY)


def test_sort_by_name_asc_desc():
    rows = _rows()
    asc = [r["name"] for r in sort_member_rows(rows, "name", "asc")]
    assert asc == ["Alpha", "Bernard", "Zoe"]
    desc = [r["name"] for r in sort_member_rows(rows, "name", "desc")]
    assert desc == ["Zoe", "Bernard", "Alpha"]


def test_sort_by_birthday():
    rows = _rows()
    asc = [r["name"] for r in sort_member_rows(rows, "birthday", "asc")]
    # le plus ancien d'échéance en premier = Bernard (2024) puis Zoe puis Alpha
    assert asc[0] == "Bernard"
    assert asc[-1] == "Alpha"


def test_sort_by_status_orders_red_first():
    rows = _rows()
    asc = [r["color"] for r in sort_member_rows(rows, "status", "asc")]
    assert asc == ["red", "orange", "green"]


def test_constants_sane():
    assert MEMBERSHIP_DAYS == 365
    assert EXPIRING_SOON_DAYS == 30
