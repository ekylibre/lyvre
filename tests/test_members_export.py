"""Tests des exports adhérents (CSV / XLSX)."""
from datetime import date

from app.views.entities import (
    EXPORT_HEADERS, _export_record, _render_members_csv, _render_members_xlsx,
)


def _row(**kw):
    base = {
        "name": "Dupont", "email": "a@b.fr", "is_member": True,
        "is_benevole": False, "notes": "note",
        "last_ha": None, "last_pos": None,
        "birthday": date(2026, 1, 1), "status": "ok", "color": "red",
        "label": "ok",
    }
    base.update(kw)
    return base


def test_export_headers_have_new_columns():
    for col in ("Bénévole", "Date anniversaire", "Statut", "Couleur"):
        assert col in EXPORT_HEADERS
    assert len(EXPORT_HEADERS) == 10


def test_export_record_values():
    rec = _export_record(_row())
    assert len(rec) == len(EXPORT_HEADERS)
    assert rec[0] == "Dupont"
    assert rec[2] == "Oui"          # Adhérent
    assert rec[3] == "Non"          # Bénévole
    assert rec[6] == "01/01/2026"   # Date anniversaire
    assert rec[7] == "ok"           # Statut
    assert rec[8] == "red"          # Couleur


def test_export_record_non_member():
    rec = _export_record(_row(is_member=False, is_benevole=True))
    assert rec[2] == "Non"
    assert rec[3] == "Oui"          # Bénévole


def test_render_csv(app):
    resp = _render_members_csv([_row()])
    assert resp.mimetype == "text/csv"
    assert "adherents.csv" in resp.headers["Content-Disposition"]
    body = resp.get_data().decode("utf-8-sig")
    assert "Date anniversaire" in body
    assert "Dupont" in body
    assert body.count(";") >= 8  # 9 colonnes -> 8 séparateurs par ligne


def test_render_xlsx(app):
    resp = _render_members_xlsx([_row(), _row(name="Martin", color="green")])
    assert resp.mimetype == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "adherents.xlsx" in resp.headers["Content-Disposition"]
    data = resp.get_data()
    assert data[:2] == b"PK"  # signature ZIP/XLSX
    assert len(data) > 0


def test_render_xlsx_empty_list(app):
    resp = _render_members_xlsx([])
    assert resp.get_data()[:2] == b"PK"
