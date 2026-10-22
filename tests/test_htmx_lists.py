"""Listes et sélecteurs en HTMX : filtres sans rechargement, recherche au fil de la frappe."""
import re
from datetime import date
from pathlib import Path

import pytest

from app.extensions import db
from app.models import (
    Account, BankAccount, Entity, FiscalYear, Journal, JournalEntry,
)

HX = {"HX-Request": "true"}
TEMPLATES = Path(__file__).resolve().parent.parent / "app" / "templates"


@pytest.fixture()
def client(app):
    app.config["LOGIN_DISABLED"] = True
    return app.test_client()


@pytest.fixture()
def data(session):
    fy = FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31))
    jr = Journal(code="OD", label="Opérations diverses")
    acc = Account(code="512", label="Banque")
    session.add_all([fy, jr, acc])
    session.flush()
    ba = BankAccount(label="Compte courant", account_id=acc.id)
    session.add(ba)
    session.add_all([
        JournalEntry(fiscal_year_id=fy.id, journal_id=jr.id, entry_date=date(2026, 3, 2),
                     reference="OD-2026-0001", description="Facture EDF mars"),
        JournalEntry(fiscal_year_id=fy.id, journal_id=jr.id, entry_date=date(2026, 3, 9),
                     reference="OD-2026-0002", description="Cotisation assurance"),
        Entity(name="Leroy Merlin", entity_type="FOURNISSEUR", email="pro@leroy.fr"),
        Entity(name="EDF", entity_type="FOURNISSEUR"),
    ])
    session.commit()
    return {"fy": fy, "ba": ba}


def _filter_form(html):
    """Premier formulaire portant des attributs hx-get."""
    m = re.search(r"<form[^>]*hx-get=[^>]*>", html)
    assert m, "aucun formulaire HTMX"
    return m.group(0)


def test_no_full_reload_selectors_left_in_templates():
    offenders = [str(p.relative_to(TEMPLATES)) for p in TEMPLATES.rglob("*.html")
                 if "this.form.submit()" in p.read_text(encoding="utf-8")]
    assert offenders == []


def test_flash_messages_not_rendered_in_htmx_page(app, client, data):
    from flask import flash

    @app.route("/_t/flash-page")
    def _t_flash_page():
        flash("Filtre appliqué", "info")
        from flask import render_template
        return render_template("base.html", nav_menus=[])

    resp = client.get("/_t/flash-page", headers=HX)
    assert "Filtre appliqué" not in resp.get_data(as_text=True)
    assert "Filtre appliqu" in resp.headers["HX-Trigger"]  # échappé en ASCII
