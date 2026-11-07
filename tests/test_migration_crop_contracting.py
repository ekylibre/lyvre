"""Migration CG2.a (f2a4b6c8d0e2) : charges 6051 des avances aux cultures reclassées en « contracting », exercices
ouverts seulement ; retour arrière. Jouée sur une base minimale."""
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

PATH = Path(__file__).parents[1] / "migrations" / "versions" / "f2a4b6c8d0e2_crop_contracting_rubric.py"
spec = importlib.util.spec_from_file_location("cg2a_migration", PATH)
cg2a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cg2a)


@pytest.fixture()
def conn(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'cg2a.db'}")
    with engine.begin() as c:
        for ddl in ("CREATE TABLE fiscal_years (id INTEGER PRIMARY KEY, status VARCHAR(10))",
                    "CREATE TABLE accounts (id INTEGER PRIMARY KEY, code VARCHAR(20))",
                    "CREATE TABLE journal_lines (id INTEGER PRIMARY KEY, account_id INTEGER)",
                    "CREATE TABLE crop_advances (id INTEGER PRIMARY KEY, fiscal_year_id INTEGER)",
                    "CREATE TABLE crop_advance_costs (id INTEGER PRIMARY KEY, crop_advance_id INTEGER, "
                    "journal_line_id INTEGER, rubric VARCHAR(12))"):
            c.execute(sa.text(ddl))
        c.execute(sa.text("INSERT INTO fiscal_years VALUES (1, 'open'), (2, 'closed')"))
        c.execute(sa.text("INSERT INTO accounts VALUES (1, '6051'), (2, '60614')"))
        c.execute(sa.text("INSERT INTO journal_lines VALUES (1, 1), (2, 2), (3, 1)"))
        c.execute(sa.text("INSERT INTO crop_advances VALUES (1, 1), (2, 2)"))
        c.execute(sa.text("INSERT INTO crop_advance_costs VALUES (1, 1, 1, 'machinery'), (2, 1, 2, 'machinery'), "
                          "(3, 2, 3, 'machinery'), (4, 1, NULL, 'machinery')"))
    with engine.begin() as c:
        yield c


def _run(conn, step):
    with Operations.context(MigrationContext.configure(conn)):
        step()


def _rubrics(conn):
    return dict(conn.execute(sa.text("SELECT id, rubric FROM crop_advance_costs")).all())


def test_upgrade_reclasses_open_6051_costs_only(conn):
    _run(conn, cg2a.upgrade)
    assert _rubrics(conn) == {1: "contracting", 2: "machinery", 3: "machinery", 4: "machinery"}
    _run(conn, cg2a.downgrade)
    assert set(_rubrics(conn).values()) == {"machinery"}


def test_entry_mode_columns_cg2b(tmp_path):
    """Migration CG2.b (a3b5c7d9e1f3) : colonnes du mode de saisie des barèmes, « monthly » par défaut ; retour arrière."""
    path = Path(__file__).parents[1] / "migrations" / "versions" / "a3b5c7d9e1f3_crop_standard_entry_mode.py"
    spec_b = importlib.util.spec_from_file_location("cg2b_migration", path)
    cg2b = importlib.util.module_from_spec(spec_b)
    spec_b.loader.exec_module(cg2b)
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'cg2b.db'}")
    with engine.begin() as c:
        c.execute(sa.text("CREATE TABLE crop_standards (id INTEGER PRIMARY KEY, production VARCHAR(120), year INTEGER)"))
        c.execute(sa.text("INSERT INTO crop_standards VALUES (1, 'Blé', 2025)"))
    with engine.begin() as c:
        _run(c, cg2b.upgrade)
        assert c.execute(sa.text("SELECT entry_mode, start_month FROM crop_standards")).one() == ("monthly", None)
        _run(c, cg2b.downgrade)
        assert "entry_mode" not in {col["name"] for col in sa.inspect(c).get_columns("crop_standards")}


def test_slow_rotation_column_cg3d(tmp_path):
    """Migration CG3.d (b4c6d8e0f2a4) : lignes déjà bloquées marquées à rotation lente ; retour arrière."""
    path = Path(__file__).parents[1] / "migrations" / "versions" / "b4c6d8e0f2a4_stock_slow_rotation.py"
    spec_d = importlib.util.spec_from_file_location("cg3d_migration", path)
    cg3d = importlib.util.module_from_spec(spec_d)
    spec_d.loader.exec_module(cg3d)
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'cg3d.db'}")
    with engine.begin() as c:
        c.execute(sa.text("CREATE TABLE stock_lines (id INTEGER PRIMARY KEY, fiscal_method VARCHAR(8))"))
        c.execute(sa.text("INSERT INTO stock_lines VALUES (1, 'frozen'), (2, 'none')"))
    with engine.begin() as c:
        _run(c, cg3d.upgrade)
        assert dict(c.execute(sa.text("SELECT id, slow_rotation FROM stock_lines")).all()) == {1: 1, 2: None}
        _run(c, cg3d.downgrade)
        assert "slow_rotation" not in {col["name"] for col in sa.inspect(c).get_columns("stock_lines")}
