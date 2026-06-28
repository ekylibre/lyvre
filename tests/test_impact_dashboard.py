"""Tests du dashboard « Visibilité & Impact » : catalogue, période, agrégats,
impact, upsert idempotent, saisie manuelle, variations."""
from datetime import date, datetime

import pytest

from app.extensions import db
from app.models import Order, OrderLine, HelloAssoOrder, HelloAssoItem, Entity, \
    TaskType, WorkTime, MetricSnapshot, ImpactFactor
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


# --- moteur d'impact ------------------------------------------------------


def test_impact_engine_with_defaults(session):
    o = Order(odoo_id=1, state="done", date_order=datetime(2026, 6, 10), amount_total_cents=5000)
    db.session.add(o); db.session.flush()
    db.session.add(OrderLine(odoo_id=1, order_id=o.id, product_name="Pull", qty=10))
    db.session.commit()

    p = ds.period_from_args({"gran": "month", "month": "2026-06"})
    out = impact_engine.compute(p)
    # 10 articles × 0.4 kg = 4 kg ; × 25 = 100 kg CO2e
    assert out["env.items_reused"] == 10
    assert out["env.weight_kg"] == pytest.approx(4.0)
    assert out["env.co2e_avoided_kg"] == pytest.approx(100.0)
    assert out["env.reuse_rate"] is None  # aucun collecté saisi


def test_impact_engine_factor_override(session):
    db.session.add(ImpactFactor(key="textile.avg_weight_kg", value=1.0, unit="kg"))
    db.session.commit()
    assert impact_engine.factor("textile.avg_weight_kg") == 1.0
    # facteur absent → défaut documenté
    assert impact_engine.factor("textile.co2e_per_kg") == 25.0


def test_impact_reuse_rate(session):
    o = Order(odoo_id=1, state="done", date_order=datetime(2026, 6, 10), amount_total_cents=100)
    db.session.add(o); db.session.flush()
    db.session.add(OrderLine(odoo_id=1, order_id=o.id, product_name="X", qty=30))
    db.session.commit()
    metrics_sync.upsert_snapshot("internal", "env.items_collected", date(2026, 6, 1), 100, "count")
    db.session.commit()
    out = impact_engine.compute(ds.period_from_args({"gran": "month", "month": "2026-06"}))
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
    resp = client.post("/impact/manual?month=2026-06", data={
        "month": "2026-06",
        "vinted.revenue_cents": "150,50",
        "vinted.items_sold": "12",
    }, follow_redirects=True)
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
