"""Migration G2 (f3b5d7e9a1c4) : mentions légales reprises de Facturation vers Structure, SIREN des
tiers, retour arrière. Jouée sur une base minimale (les trois tables concernées)."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

PATH = Path(__file__).parents[1] / "migrations" / "versions" / "f3b5d7e9a1c4_legal_mentions_in_organization.py"
spec = importlib.util.spec_from_file_location("g2_migration", PATH)
g2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2)


@pytest.fixture()
def conn(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'g2.db'}")
    with engine.begin() as c:
        c.execute(sa.text("CREATE TABLE organization (id INTEGER PRIMARY KEY, name VARCHAR(200) NOT NULL, "
                          "siren VARCHAR(9), legal_form VARCHAR(100), rcs_city VARCHAR(100))"))
        c.execute(sa.text("CREATE TABLE billing_settings (id INTEGER PRIMARY KEY, legal_form VARCHAR(100), "
                          "share_capital_cents INTEGER, rcs VARCHAR(100), vat_number VARCHAR(20), iban VARCHAR(34))"))
        c.execute(sa.text("CREATE TABLE entities (id INTEGER PRIMARY KEY, name VARCHAR(200), siret VARCHAR(14))"))
    with engine.begin() as c:
        yield c


def _run(conn, step):
    with Operations.context(MigrationContext.configure(conn)):
        step()


def _org(conn):
    return conn.execute(sa.text("SELECT legal_form, share_capital_cents, rcs_city, vat_number FROM organization")).one()


@pytest.mark.parametrize("text, city", [
    ("RCS Saintes 840 968 499", "Saintes"), ("RCS Saintes B 840 968 499", "Saintes"),
    ("840 968 499 RCS La Rochelle", "La Rochelle"), ("RCS de Saintes", "Saintes"), ("RCS d'Angers", "Angers"),
    ("Saintes", None), ("", None),
])
def test_rcs_city(text, city):
    assert g2.rcs_city(text) == city


def test_copy_into_empty_structure(conn, capsys):
    conn.execute(sa.text("INSERT INTO organization (id, name, siren) VALUES (1, 'SCI', '840968499')"))
    conn.execute(sa.text("INSERT INTO billing_settings (id, legal_form, share_capital_cents, rcs, vat_number, iban) "
                         "VALUES (1, 'SCI', 27489000, 'RCS Saintes 840 968 499', 'fr 32 840968499', 'FR76')"))
    conn.execute(sa.text("INSERT INTO entities (id, name, siret) VALUES (1, 'A', '73282932000074'), (2, 'B', NULL), "
                         "(3, 'C', '732829320'), (4, 'D', '12AB')"))
    _run(conn, g2.upgrade)
    assert tuple(_org(conn)) == ("SCI", 27489000, "Saintes", "FR32840968499")
    assert dict(conn.execute(sa.text("SELECT name, siren FROM entities")).all()) == \
        {"A": "732829320", "B": None, "C": "732829320", "D": None}
    columns = {c["name"] for c in sa.inspect(conn).get_columns("billing_settings")}
    assert columns == {"id", "iban"}
    assert "repris de Facturation" in capsys.readouterr().out

    _run(conn, g2.downgrade)
    row = conn.execute(sa.text("SELECT legal_form, share_capital_cents, rcs, vat_number FROM billing_settings")).one()
    assert tuple(row) == ("SCI", 27489000, "RCS Saintes 840 968 499", "FR32840968499")
    assert "vat_number" not in {c["name"] for c in sa.inspect(conn).get_columns("organization")}


def test_conflict_keeps_structure_and_is_logged(conn, capsys):
    conn.execute(sa.text("INSERT INTO organization (id, name, legal_form, rcs_city) "
                         "VALUES (1, 'SCI', 'Société civile immobilière', 'Saintes')"))
    conn.execute(sa.text("INSERT INTO billing_settings (id, legal_form, rcs) VALUES (1, 'SCI', 'RCS Saintes')"))
    _run(conn, g2.upgrade)
    assert tuple(_org(conn)) == ("Société civile immobilière", None, "Saintes", None)
    out = capsys.readouterr().out
    assert "[G2] forme juridique : Structure « Société civile immobilière » conservée, Facturation « SCI » ignorée." in out
    assert "greffe" not in out  # même valeur des deux côtés : pas d'avertissement


def test_unreadable_rcs_is_logged(conn, capsys):
    conn.execute(sa.text("INSERT INTO organization (id, name) VALUES (1, 'SCI')"))
    conn.execute(sa.text("INSERT INTO billing_settings (id, rcs) VALUES (1, 'Saintes')"))
    _run(conn, g2.upgrade)
    assert _org(conn).rcs_city is None
    assert "RCS « Saintes » illisible" in capsys.readouterr().out
