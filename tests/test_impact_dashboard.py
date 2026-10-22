"""Tests du dashboard « Visibilité & Impact » : catalogue, période, agrégats,
impact, upsert idempotent, saisie manuelle, variations."""
from datetime import date, datetime

import pytest

from app.extensions import db
from app.models import Order, OrderLine, HelloAssoOrder, HelloAssoItem, Entity, \
    TaskType, WorkTime, MetricSnapshot, ImpactFactor, EcoDeclaration
from app.services import metric_catalog as cat
from app.services import dashboard_service as ds
from app.services import metrics_aggregator, impact_engine, metrics_sync


@pytest.fixture()
def client(app):
    app.config["LOGIN_DISABLED"] = True
    return app.test_client()


# --- catalogue ------------------------------------------------------------


def test_catalog_keys_unique_and_valid():
    keys = [m.key for m in cat.METRICS]
    assert len(keys) == len(set(keys))
    dims = {d for d, _ in cat.DIMENSIONS}
    for m in cat.METRICS:
        assert m.dimension in dims
        assert m.origin in ("live", "snapshot", "manual")
        assert m.aggregation in ("sum", "last")


def test_manual_and_snapshot_sets():
    manual = {m.key for m in cat.manual_metrics()}
    assert "vinted.items_sold" in manual
    assert "facebook_group.members" in manual
    # manuel ⊆ snapshot (les manuels sont aussi stockés)
    snap = {m.key for m in cat.snapshot_metrics()}
    assert manual <= snap


# --- période --------------------------------------------------------------


def test_period_month_and_previous():
    p = ds.period_from_args({"gran": "month", "month": "2026-06"})
    assert p.start == date(2026, 6, 1) and p.end == date(2026, 7, 1)
    assert "2026" in p.label
    prev = p.previous()
    assert prev.start == date(2026, 5, 1) and prev.end == date(2026, 6, 1)


def test_period_quarter_year_custom():
    q = ds.period_from_args({"gran": "quarter", "quarter": "2026-Q2"})
    assert q.start == date(2026, 4, 1) and q.end == date(2026, 7, 1)
    y = ds.period_from_args({"gran": "year", "year": "2026"})
    assert y.start == date(2026, 1, 1) and y.end == date(2027, 1, 1)
    c = ds.period_from_args({"gran": "custom", "start": "2026-06-01", "end": "2026-06-15"})
    assert c.start == date(2026, 6, 1) and c.end == date(2026, 6, 16)


def test_period_default_is_current_month():
    p = ds.period_from_args({}, today=date(2026, 3, 10))
    assert p.start == date(2026, 3, 1)


# --- agrégats internes ----------------------------------------------------


def test_economic_aggregator(session):
    db.session.add(Order(odoo_id=1, state="done", date_order=datetime(2026, 6, 10), amount_total_cents=5000))
    db.session.add(Order(odoo_id=2, state="paid", date_order=datetime(2026, 6, 15), amount_total_cents=2500))
    db.session.add(Order(odoo_id=3, state="draft", date_order=datetime(2026, 6, 15), amount_total_cents=9999))
    ho = HelloAssoOrder(helloasso_id=1, date=datetime(2026, 6, 5), amount_total_cents=4000)
    db.session.add(ho); db.session.flush()
    db.session.add(HelloAssoItem(helloasso_id=1, order_id=ho.id, type="Donation", amount_cents=3000))
    db.session.add(HelloAssoItem(helloasso_id=2, order_id=ho.id, type="Membership", amount_cents=1000))
    db.session.commit()

    p = ds.period_from_args({"gran": "month", "month": "2026-06"})
    eco = metrics_aggregator.economic(p)
    assert eco["econ.pos_revenue_cents"] == 7500  # draft exclu
    assert eco["econ.donations_cents"] == 3000
    assert eco["econ.memberships_cents"] == 1000


def test_social_aggregator(session):
    ent = Entity(name="Bob", is_benevole=True, is_member=True)
    tt = TaskType(name="Caisse", hourly_rate_cents=2500)
    db.session.add_all([ent, tt]); db.session.commit()
    db.session.add(WorkTime(entity_id=ent.id, task_type_id=tt.id, work_date=date(2026, 6, 12), hours=4))
    db.session.commit()

    p = ds.period_from_args({"gran": "month", "month": "2026-06"})
    soc = metrics_aggregator.social(p)
    assert soc["social.active_volunteers"] == 1
    assert soc["social.volunteer_hours"] == 4.0
    assert soc["social.volunteer_value_cents"] == 10000  # 4 × 2500
    assert soc["social.members_count"] == 1


def test_active_volunteers_is_distinct_per_month(session):
    """« Bénévoles actifs » = nb de bénévoles UNIQUES ayant saisi des heures
    dans le mois (dédupliqué, et borné au mois)."""
    alice = Entity(name="Alice", is_benevole=True)
    bob = Entity(name="Bob", is_benevole=True)
    carol = Entity(name="Carol", is_benevole=True)
    tt = TaskType(name="Tri", hourly_rate_cents=2000)
    db.session.add_all([alice, bob, carol, tt])
    db.session.commit()

    db.session.add_all([
        # Alice saisit DEUX fois en juin → comptée une seule fois.
        WorkTime(entity_id=alice.id, task_type_id=tt.id, work_date=date(2026, 6, 3), hours=2),
        WorkTime(entity_id=alice.id, task_type_id=tt.id, work_date=date(2026, 6, 20), hours=3),
        # Bob saisit une fois en juin.
        WorkTime(entity_id=bob.id, task_type_id=tt.id, work_date=date(2026, 6, 15), hours=1),
        # Carol ne saisit qu'en mai → hors juin.
        WorkTime(entity_id=carol.id, task_type_id=tt.id, work_date=date(2026, 5, 28), hours=5),
    ])
    db.session.commit()

    june = ds.period_from_args({"gran": "month", "month": "2026-06"})
    assert metrics_aggregator.social(june)["social.active_volunteers"] == 2  # Alice, Bob

    may = ds.period_from_args({"gran": "month", "month": "2026-05"})
    assert metrics_aggregator.social(may)["social.active_volunteers"] == 1   # Carol

    july = ds.period_from_args({"gran": "month", "month": "2026-07"})
    assert metrics_aggregator.social(july)["social.active_volunteers"] == 0


# --- moteur d'impact ------------------------------------------------------


def test_impact_engine_from_tonnages(session):
    # T2 2026 : 5 t collectées / 2 t réemployées de meubles (facteur défaut 1200 kgCO2e/t).
    db.session.add(EcoDeclaration(
        organism="ecomaison", material="Meubles", quarter_label="T2 2026",
        period_start=date(2026, 4, 1), entrant_t=5, sortant_t=2))
    db.session.commit()

    out = impact_engine.compute(ds.period_from_args({"gran": "year", "year": "2026"}))
    assert out["env.collected_kg"] == pytest.approx(5000.0)
    assert out["env.weight_kg"] == pytest.approx(2000.0)        # 2 t réemployées
    assert out["env.co2e_avoided_kg"] == pytest.approx(2400.0)  # 2 × 1200
    assert out["env.reuse_rate"] == pytest.approx(2 / 5)
    assert out["env.car_km_equiv"] == pytest.approx(2400.0 * 5.18)  # facteur km défaut


def test_impact_engine_no_data_returns_empty(session):
    # Aucune déclaration sur la période → dict vide (indicateurs « — »).
    assert impact_engine.compute(ds.period_from_args({"gran": "month", "month": "2026-06"})) == {}


def test_impact_engine_factor_override(session):
    db.session.add(ImpactFactor(key="reemploi.meubles.co2e_per_t", value=900.0,
                                unit="co2e_kg_per_t"))
    db.session.commit()
    assert impact_engine.factor("reemploi.meubles.co2e_per_t") == 900.0
    # facteur absent → défaut documenté
    assert impact_engine.factor("reemploi.d3e.co2e_per_t") == 3000.0


def test_impact_reuse_rate(session):
    db.session.add(EcoDeclaration(
        organism="ecologic", material="D3E", quarter_label="T2 2026",
        period_start=date(2026, 4, 1), entrant_t=10, sortant_t=3))
    db.session.commit()
    out = impact_engine.compute(ds.period_from_args({"gran": "quarter", "quarter": "2026-Q2"}))
    assert out["env.reuse_rate"] == pytest.approx(0.30)


# --- upsert idempotent ----------------------------------------------------


def test_upsert_idempotent(session):
    metrics_sync.upsert_snapshot("vinted", "vinted.followers", date(2026, 6, 1), 100, "count")
    db.session.commit()
    metrics_sync.upsert_snapshot("vinted", "vinted.followers", date(2026, 6, 1), 150, "count")
    db.session.commit()
    rows = MetricSnapshot.query.filter_by(metric_key="vinted.followers").all()
    assert len(rows) == 1
    assert float(rows[0].value) == 150.0


# --- saisie manuelle (route) ----------------------------------------------


def test_manual_entry_euros_to_cents(client, session):
    resp = client.put("/api/v1/impact/manual", json={"month": "2026-06", "values": {
        "vinted.revenue_cents": "150,50",
        "vinted.items_sold": "12",
    }})
    assert resp.status_code == 200
    rev = MetricSnapshot.query.filter_by(metric_key="vinted.revenue_cents").first()
    assert float(rev.value) == 15050  # euros → cents
    sold = MetricSnapshot.query.filter_by(metric_key="vinted.items_sold").first()
    assert float(sold.value) == 12


# --- variations & agrégation ---------------------------------------------


def test_dashboard_delta_pct(session):
    db.session.add(Order(odoo_id=1, state="done", date_order=datetime(2026, 6, 10), amount_total_cents=7500))
    db.session.add(Order(odoo_id=2, state="done", date_order=datetime(2026, 5, 10), amount_total_cents=3000))
    db.session.commit()
    view = ds.build_dashboard(ds.period_from_args({"gran": "month", "month": "2026-06"}))
    pos = next(k for k in view.sections["economic"] if k.key == "econ.pos_revenue_cents")
    assert pos.value == 7500
    assert pos.delta_pct == pytest.approx(150.0)  # (7500-3000)/3000


def test_snapshot_aggregation_sum_vs_last(session):
    # deux mois dans un trimestre
    metrics_sync.upsert_snapshot("ga4", "ga4.sessions", date(2026, 4, 1), 100, "count")
    metrics_sync.upsert_snapshot("ga4", "ga4.sessions", date(2026, 5, 1), 50, "count")
    metrics_sync.upsert_snapshot("facebook_page", "facebook_page.followers", date(2026, 4, 1), 200, "count")
    metrics_sync.upsert_snapshot("facebook_page", "facebook_page.followers", date(2026, 5, 1), 250, "count")
    db.session.commit()
    q = ds.period_from_args({"gran": "quarter", "quarter": "2026-Q2"})
    vals = ds._resolve_values(q)
    assert vals["ga4.sessions"] == 150          # sum
    assert vals["facebook_page.followers"] == 250  # last (stock)


def test_format_value():
    euros = cat.get("econ.pos_revenue_cents")
    assert ds.format_value(euros, 12345) == "123,45 €"
    pct = cat.get("social.renewal_rate")
    assert ds.format_value(pct, 0.5) == "50,0 %"
    assert ds.format_value(euros, None) == "—"


# --- provenance / source des indicateurs ----------------------------------


def test_source_label_provenance():
    """Chaque indicateur expose une provenance lisible selon source + origine."""
    assert ds.source_label(cat.get("ga4.active_users")) == \
        "Google Analytics (GA4) — API synchronisée"
    assert ds.source_label(cat.get("vinted.revenue_cents")) == "Vinted — saisie manuelle"
    assert ds.source_label(cat.get("facebook_group.members")) == \
        "Facebook — Groupe — saisie manuelle"
    assert "Données internes" in ds.source_label(cat.get("econ.pos_revenue_cents"))
    assert "Calculé" in ds.source_label(cat.get("env.co2e_avoided_kg"))


def test_kpi_carries_source_label(session):
    period = ds.period_from_args({"gran": "month", "month": "2026-03"})
    view = ds.build_dashboard(period)
    kpi = next(k for k in view.sections["visibility"] if k.key == "ga4.active_users")
    assert kpi.source_label == "Google Analytics (GA4) — API synchronisée"


# --- sélecteurs d'années / mois sur tous les exercices ---------------------


def test_year_and_month_options_span_all_fiscal_years(session):
    from app.models import FiscalYear
    from app.utils.list_filters import year_options_all_fy, month_options_all_fy
    db.session.add_all([
        FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31)),
        FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)),
    ])
    db.session.commit()

    assert year_options_all_fy() == [2026, 2025]      # décroissant
    months = {o["value"] for o in month_options_all_fy()}
    assert "2025-01" in months and "2025-12" in months and "2026-06" in months


# --- synchro GA4 d'une année entière ---------------------------------------


def test_sync_metrics_year_creates_monthly_snapshots(session, monkeypatch):
    """sync_metrics_year récupère l'année en 1 appel et upsert un snapshot par mois."""
    class _FakeGA4:
        def fetch_year(self, year):
            return {
                (year, 1): {"ga4.active_users": 100.0, "ga4.sessions": 120.0},
                (year, 2): {"ga4.active_users": 80.0},
            }

    monkeypatch.setattr("app.services.ga4_client.from_app_config", lambda: _FakeGA4())

    result = metrics_sync.sync_metrics_year(2025)
    assert result["ga4"]["imported"] == 3

    jan = MetricSnapshot.query.filter_by(
        source="ga4", metric_key="ga4.active_users", period_start=date(2025, 1, 1),
    ).first()
    assert jan is not None and float(jan.value) == 100.0
    feb = MetricSnapshot.query.filter_by(
        source="ga4", metric_key="ga4.active_users", period_start=date(2025, 2, 1),
    ).first()
    assert feb is not None and float(feb.value) == 80.0
