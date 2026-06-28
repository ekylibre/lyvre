"""Assemblage du dashboard « Visibilité & Impact ».

Fusionne trois origines de données en un modèle de vue unique :
- **live** : agrégats internes (éco/social) + impact environnemental, recalculés.
- **snapshot** : métriques API (GA4, Facebook) stockées.
- **manual** : saisies (Vinted, groupe FB) stockées.

Calcule, par métrique du catalogue, la valeur de la période, la variation vs la
période précédente et une mini-tendance (N dernières périodes).
"""
from dataclasses import dataclass, field
from datetime import date

from app.extensions import db
from app.models import MetricSnapshot
from app.services import metric_catalog as catalog
from app.utils.list_filters import MONTHS_FR

TREND_POINTS = 6

# Libellés des sources externes (pour le bandeau de fraîcheur).
SOURCE_LABELS = {
    "ga4": "Google Analytics",
    "facebook_page": "Facebook (Page)",
    "facebook_group": "Facebook (Groupe)",
    "vinted": "Vinted",
}


# ---------------------------------------------------------------------------
# Période
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Period:
    start: date          # inclus
    end: date            # exclu
    gran: str            # 'month' | 'quarter' | 'year' | 'custom'
    label: str

    def previous(self) -> "Period":
        return _shift(self, -1)


def _month_period(y, m) -> Period:
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return Period(start, end, "month", f"{MONTHS_FR[m - 1]} {y}")


def _quarter_period(y, q) -> Period:
    m = (q - 1) * 3 + 1
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m + 3 > 12 else date(y, m + 3, 1)
    return Period(start, end, "quarter", f"T{q} {y}")


def _year_period(y) -> Period:
    return Period(date(y, 1, 1), date(y + 1, 1, 1), "year", f"Année {y}")


def _custom_period(start, end_incl) -> Period:
    from datetime import timedelta
    end = end_incl + timedelta(days=1)
    label = f"{start.strftime('%d/%m/%Y')} – {end_incl.strftime('%d/%m/%Y')}"
    return Period(start, end, "custom", label)


def _shift(period: Period, n: int) -> Period:
    """Décale une période de n unités de même granularité (n négatif = passé)."""
    s = period.start
    if period.gran == "month":
        total = s.year * 12 + (s.month - 1) + n
        return _month_period(total // 12, total % 12 + 1)
    if period.gran == "quarter":
        q0 = (s.month - 1) // 3
        total = s.year * 4 + q0 + n
        return _quarter_period(total // 4, total % 4 + 1)
    if period.gran == "year":
        return _year_period(s.year + n)
    # custom : fenêtre de même longueur, glissée
    length = (period.end - period.start).days
    from datetime import timedelta
    new_start = period.start + timedelta(days=length * n)
    return _custom_period(new_start, new_start + timedelta(days=length - 1))


def _parse_date(s):
    from datetime import datetime
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def period_for_fiscal_year(fy) -> Period:
    """Période couvrant un exercice comptable (FiscalYear), pour le rapport d'activité."""
    from datetime import timedelta
    return Period(fy.start_date, fy.end_date + timedelta(days=1), "custom", fy.label)


def period_from_args(args, today=None) -> Period:
    """Construit la période depuis les query args (défaut : mois courant)."""
    today = today or date.today()
    gran = (args.get("gran") or "month").strip().lower()

    if gran == "year":
        try:
            return _year_period(int(args.get("year") or today.year))
        except ValueError:
            return _year_period(today.year)

    if gran == "quarter":
        ref = (args.get("quarter") or "").strip()  # 'YYYY-Qn'
        try:
            y, q = ref.upper().split("-Q")
            return _quarter_period(int(y), int(q))
        except (ValueError, AttributeError):
            return _quarter_period(today.year, (today.month - 1) // 3 + 1)

    if gran == "custom":
        start = _parse_date(args.get("start"))
        end = _parse_date(args.get("end"))
        if start and end and end >= start:
            return _custom_period(start, end)
        return _month_period(today.year, today.month)

    # month (défaut)
    ref = (args.get("month") or "").strip()  # 'YYYY-MM'
    try:
        from datetime import datetime
        dt = datetime.strptime(ref, "%Y-%m")
        return _month_period(dt.year, dt.month)
    except ValueError:
        return _month_period(today.year, today.month)


# ---------------------------------------------------------------------------
# Modèle de vue
# ---------------------------------------------------------------------------

@dataclass
class Kpi:
    key: str
    label: str
    dimension: str
    unit: str
    fmt: str
    value: float | None
    formatted: str
    delta_pct: float | None
    trend: list = field(default_factory=list)
    source: str = ""
    origin: str = ""
    higher_is_better: bool = True
    available: bool = False


@dataclass
class DashboardView:
    period: Period
    sections: dict           # dimension -> [Kpi]
    highlights: list         # [Kpi-like dict]
    sources_status: list     # [{source, label, fresh_at, status}]


# ---------------------------------------------------------------------------
# Résolution des valeurs
# ---------------------------------------------------------------------------

def _live_values(period: Period) -> dict:
    """Métriques recalculées (interne éco/social + impact). Rempli en phases 2-3."""
    values = {}
    try:
        from app.services import metrics_aggregator
        values.update(metrics_aggregator.economic(period))
        values.update(metrics_aggregator.social(period))
    except Exception:
        pass
    try:
        from app.services import impact_engine
        values.update(impact_engine.compute(period))
    except Exception:
        pass
    return values


def _snapshot_values(period: Period) -> dict:
    """Métriques stockées (GA4, Facebook, manuel) agrégées sur la période."""
    rows = (
        db.session.query(MetricSnapshot)
        .filter(MetricSnapshot.period_start >= period.start)
        .filter(MetricSnapshot.period_start < period.end)
        .all()
    )
    # Regroupe par metric_key, puis applique sum/last selon le catalogue.
    by_key = {}
    for r in rows:
        by_key.setdefault(r.metric_key, []).append(r)

    values = {}
    for key, snaps in by_key.items():
        metric = catalog.get(key)
        agg = metric.aggregation if metric else "sum"
        snaps.sort(key=lambda s: s.period_start)
        nums = [float(s.value) for s in snaps]
        values[key] = nums[-1] if agg == "last" else sum(nums)
    return values


def _resolve_values(period: Period) -> dict:
    values = {}
    values.update(_live_values(period))
    values.update(_snapshot_values(period))
    return values


# ---------------------------------------------------------------------------
# Formatage
# ---------------------------------------------------------------------------

def _fr(n, dec=0):
    return f"{n:,.{dec}f}".replace(",", " ").replace(".", ",")


def format_value(metric, value) -> str:
    if value is None:
        return "—"
    fmt = metric.fmt
    if fmt == "euros":
        return f"{_fr(value / 100, 2)} €"
    if fmt == "int":
        return _fr(round(value), 0)
    if fmt == "percent":
        return f"{_fr(value * 100, 1)} %"
    if fmt == "duration":
        secs = int(round(value))
        return f"{secs // 60} min {secs % 60:02d} s"
    if fmt == "decimal":
        suffix = {"kg": " kg", "co2e_kg": " kg CO₂e", "liters": " L",
                  "hours": " h"}.get(metric.unit, "")
        return f"{_fr(value, 1)}{suffix}"
    return _fr(value, 0)


def _delta_pct(value, prev):
    if value is None or prev in (None, 0):
        return None
    return (value - prev) / abs(prev) * 100.0


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def _sources_status(period: Period) -> list:
    """Fraîcheur par source externe/manuelle, pour le bandeau."""
    rows = (
        db.session.query(
            MetricSnapshot.source, db.func.max(MetricSnapshot.captured_at)
        )
        .group_by(MetricSnapshot.source)
        .all()
    )
    fresh = {src: ts for src, ts in rows}
    status = []
    for src, label in SOURCE_LABELS.items():
        ts = fresh.get(src)
        status.append({
            "source": src,
            "label": label,
            "fresh_at": ts,
            "status": "ok" if ts else "pending",
        })
    return status


def _highlights(values: dict, prev: dict) -> list:
    """Indicateurs phares agrégés (audience totale, CA total, équivalent CO₂)."""
    def agg_sum(keys, src):
        present = [values.get(k) for k in keys if values.get(k) is not None]
        return sum(present) if present else None

    items = []

    audience_keys = ["ga4.active_users", "facebook_page.followers",
                     "facebook_group.members", "vinted.followers"]
    audience = agg_sum(audience_keys, values)
    items.append({
        "key": "agg.total_audience", "label": "Audience totale",
        "formatted": _fr(round(audience), 0) if audience is not None else "—",
        "available": audience is not None, "icon": "📣",
    })

    rev_keys = ["econ.pos_revenue_cents", "vinted.revenue_cents",
                "econ.donations_cents", "econ.memberships_cents"]
    revenue = agg_sum(rev_keys, values)
    items.append({
        "key": "agg.total_revenue", "label": "Ressources totales",
        "formatted": f"{_fr((revenue or 0) / 100, 2)} €" if revenue is not None else "—",
        "available": revenue is not None, "icon": "💶",
    })

    co2 = values.get("env.co2e_avoided_kg")
    items.append({
        "key": "agg.co2_avoided", "label": "CO₂ évité",
        "formatted": f"{_fr(co2, 1)} kg CO₂e" if co2 is not None else "—",
        "available": co2 is not None, "icon": "🌱",
    })

    hours = values.get("social.volunteer_hours")
    items.append({
        "key": "agg.volunteer_hours", "label": "Heures de bénévolat",
        "formatted": f"{_fr(hours, 1)} h" if hours is not None else "—",
        "available": hours is not None, "icon": "🤝",
    })
    return items


def build_dashboard(period: Period) -> DashboardView:
    values = _resolve_values(period)
    prev_values = _resolve_values(period.previous())

    # Tendance : N dernières périodes de même granularité.
    trend_periods = []
    p = period
    for _ in range(TREND_POINTS):
        trend_periods.append(p)
        p = p.previous()
    trend_periods.reverse()
    trend_values = [_resolve_values(tp) for tp in trend_periods]

    sections = {}
    for dim, _label in catalog.DIMENSIONS:
        kpis = []
        for metric in catalog.by_dimension(dim):
            value = values.get(metric.key)
            prev = prev_values.get(metric.key)
            kpis.append(Kpi(
                key=metric.key, label=metric.label, dimension=dim,
                unit=metric.unit, fmt=metric.fmt, value=value,
                formatted=format_value(metric, value),
                delta_pct=_delta_pct(value, prev),
                trend=[tv.get(metric.key) for tv in trend_values],
                source=metric.source, origin=metric.origin,
                higher_is_better=metric.higher_is_better,
                available=value is not None,
            ))
        sections[dim] = kpis

    return DashboardView(
        period=period,
        sections=sections,
        highlights=_highlights(values, prev_values),
        sources_status=_sources_status(period),
    )
