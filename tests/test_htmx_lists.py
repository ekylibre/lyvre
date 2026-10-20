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


@pytest.mark.parametrize("url_name, target", [
    ("entries", "#list"),
    ("transactions", "#page-content"),
    ("payouts", "#page-content"),
    ("orders", "#page-content"),
    ("customer_invoices", "#list"),
    ("work_times", "#page-content"),
    ("entities", "#list"),
    ("members", "#list"),
    ("balance", "#page-content"),
    ("grand_livre", "#page-content"),
    ("bilan", "#page-content"),
    ("compte_resultat", "#page-content"),
    ("dashboard", "#page-content"),
])
def test_filter_form_is_htmx(client, data, url_name, target):
    urls = {
        "entries": "/entries/",
        "transactions": f"/bank-accounts/{data['ba'].id}/transactions",
        "payouts": "/payouts/",
        "orders": "/orders/",
        "customer_invoices": "/customer-invoices/",
        "work_times": "/work-times/",
        "entities": "/entities/",
        "members": "/entities/members",
        "balance": "/reports/balance",
        "grand_livre": "/reports/grand-livre",
        "bilan": "/reports/bilan",
        "compte_resultat": "/reports/compte-de-resultat",
        "dashboard": "/",
    }
    resp = client.get(urls[url_name])
    assert resp.status_code == 200, resp.status_code
    html = resp.get_data(as_text=True)
    assert 'id="page-content"' in html
    form = _filter_form(html)
    assert f'hx-target="{target}"' in form and f'hx-select="{target}"' in form
    assert 'hx-push-url="true"' in form
    assert "change, submit" in form
    # La zone ciblée existe et n'inclut pas le champ de recherche (pas écrasé pendant la frappe).
    if target == "#list":
        assert 'id="list"' in html
        assert "input changed delay:300ms" in form
        list_zone = html.split('id="list"', 1)[1]
        assert 'type="search"' not in list_zone


def test_sort_header_navigates_with_htmx(client, data):
    html = client.get("/entries/").get_data(as_text=True)
    link = re.search(r'<a href="[^"]*sort=asc[^"]*"[^>]*>', html).group(0)
    assert "hx-get=" in link and 'hx-target="#page-content"' in link
    assert 'hx-push-url="true"' in link


def test_htmx_request_returns_page_with_selectable_zone(client, data):
    resp = client.get("/entries/?month=2026-03", headers=HX)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert 'id="list"' in html and "OD-2026-0001" in html


def test_entries_search(client, data):
    html = client.get("/entries/?q=edf", headers=HX).get_data(as_text=True)
    assert "OD-2026-0001" in html and "OD-2026-0002" not in html
    html = client.get("/entries/?q=OD-2026-0002").get_data(as_text=True)
    assert "OD-2026-0002" in html and "Facture EDF" not in html


def test_entities_search_by_name_and_email(client, data):
    html = client.get("/entities/?q=leroy.fr").get_data(as_text=True)
    assert "Leroy Merlin" in html and ">EDF<" not in html
    html = client.get("/entities/?q=zzz").get_data(as_text=True)
    assert "Aucune entité ne correspond" in html


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
