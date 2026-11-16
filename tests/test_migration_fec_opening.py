"""Migration d5f7b9c1e3a6 : les à-nouveaux d'un FEC importé deviennent des écritures d'ouverture (10/11/2026).
Jouée sur une base minimale (les tables concernées)."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

PATH = Path(__file__).parents[1] / "migrations" / "versions" / "d5f7b9c1e3a6_fec_opening_entries.py"
spec = importlib.util.spec_from_file_location("fec_opening_migration", PATH)
mig = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mig)


@pytest.fixture()
def conn(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    with engine.begin() as c:
        for ddl in ("CREATE TABLE fiscal_years (id INTEGER PRIMARY KEY, start_date DATE)",
                    "CREATE TABLE journals (id INTEGER PRIMARY KEY, code VARCHAR(10))",
                    "CREATE TABLE accounts (id INTEGER PRIMARY KEY, code VARCHAR(20))",
                    "CREATE TABLE journal_entries (id INTEGER PRIMARY KEY, fiscal_year_id INTEGER, journal_id INTEGER, "
                    "entry_date DATE, source VARCHAR(30), source_ref VARCHAR(200))",
                    "CREATE TABLE journal_lines (id INTEGER PRIMARY KEY, entry_id INTEGER, account_id INTEGER)"):
            c.execute(sa.text(ddl))
        c.execute(sa.text("INSERT INTO fiscal_years VALUES (1, '2024-02-01'), (2, '2025-02-01')"))
        c.execute(sa.text("INSERT INTO journals VALUES (1, 'AN'), (2, 'OD')"))
        c.execute(sa.text("INSERT INTO accounts VALUES (1, '241'), (2, '101'), (3, '7011')"))
        c.execute(sa.text("""INSERT INTO journal_entries VALUES
            (1, 1, 1, '2024-02-01', 'FEC_IMPORT', 'AN1'),     -- à-nouveaux : requalifié
            (2, 1, 2, '2024-02-01', 'FEC_IMPORT', 'OD1'),     -- autre journal
            (3, 1, 1, '2024-03-01', 'FEC_IMPORT', 'AN2'),     -- pas le premier jour
            (4, 2, 1, '2025-02-01', 'FEC_IMPORT', 'AN3'),     -- touche un compte de produit
            (5, 2, 1, '2025-02-01', 'OPENING', NULL)"""))
        c.execute(sa.text("INSERT INTO journal_lines VALUES (1, 1, 1), (2, 1, 2), (3, 2, 1), (4, 3, 1), (5, 4, 1), (6, 4, 3)"))
    with engine.begin() as c:
        yield c


def _run(conn, step):
    with Operations.context(MigrationContext.configure(conn)):
        step()


def _sources(conn):
    return dict(conn.execute(sa.text("SELECT id, source FROM journal_entries")).all())


def test_upgrade_then_downgrade(conn):
    _run(conn, mig.upgrade)
    assert _sources(conn) == {1: "OPENING", 2: "FEC_IMPORT", 3: "FEC_IMPORT", 4: "FEC_IMPORT", 5: "OPENING"}
    _run(conn, mig.downgrade)
    assert _sources(conn) == {1: "FEC_IMPORT", 2: "FEC_IMPORT", 3: "FEC_IMPORT", 4: "FEC_IMPORT", 5: "OPENING"}
