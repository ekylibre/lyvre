"""Moteur d'impact environnemental (réemploi).

Convertit les ventes/dons en indicateurs physiques (kg détournés, CO₂ évité, eau
économisée) via des facteurs ADEME paramétrables (`impact_factors`). Calculé en
direct ; les saisies manuelles (Vinted, dons, collectés) sont lues depuis
`metric_snapshots`.
"""
from app.extensions import db
from app.models import Order, OrderLine, ImpactFactor, MetricSnapshot

POS_REVENUE_STATES = ("paid", "done", "invoiced")


# Valeurs par défaut — ordres de grandeur ADEME / Refashion, **à valider** par le
# bureau avant communication externe. (unit, default, libellé, url)
DEFAULT_FACTORS = {
    "textile.avg_weight_kg": ("kg", 0.400,
                              "ADEME Base Empreinte — à valider",
                              "https://base-empreinte.ademe.fr"),
    "textile.co2e_per_kg": ("co2e_kg", 25.0,
                            "ADEME Base Empreinte — à valider",
                            "https://base-empreinte.ademe.fr"),
    "textile.water_l_per_kg": ("liters", 5000.0,
                               "ADEME Base Empreinte — à valider",
                               "https://base-empreinte.ademe.fr"),
    "equiv.car_km_per_co2e_kg": ("km", 5.18,
                                 "ADEME — 0,193 kg CO₂e/km (voiture moyenne)",
                                 "https://base-empreinte.ademe.fr"),
    # Facteurs de réemploi par matière (kg CO₂e évités par TONNE réemployée).
    # Ordres de grandeur ADEME — **à valider** par le bureau.
    "reemploi.meubles.co2e_per_t": ("co2e_kg_per_t", 1200.0,
                                    "ADEME Base Empreinte — à valider",
                                    "https://base-empreinte.ademe.fr"),
    "reemploi.jouets.co2e_per_t": ("co2e_kg_per_t", 2000.0,
                                   "ADEME Base Empreinte — à valider",
                                   "https://base-empreinte.ademe.fr"),
    "reemploi.brico-jardin.co2e_per_t": ("co2e_kg_per_t", 1500.0,
                                         "ADEME Base Empreinte — à valider",
                                         "https://base-empreinte.ademe.fr"),
    "reemploi.d3e.co2e_per_t": ("co2e_kg_per_t", 3000.0,
                                "ADEME Base Empreinte — à valider",
                                "https://base-empreinte.ademe.fr"),
    "reemploi.sports.co2e_per_t": ("co2e_kg_per_t", 1800.0,
                                   "ADEME Base Empreinte — à valider",
                                   "https://base-empreinte.ademe.fr"),
}


def factor(key, default=None):
    """Valeur d'un facteur : base d'abord, sinon défaut documenté, sinon `default`."""
    row = db.session.query(ImpactFactor).filter_by(key=key).first()
    if row is not None:
        return float(row.value)
    if key in DEFAULT_FACTORS:
        return DEFAULT_FACTORS[key][1]
    return default


def _manual_sum(period, metric_key):
    """Somme des saisies manuelles d'une métrique sur la période."""
    total = db.session.query(
        db.func.coalesce(db.func.sum(MetricSnapshot.value), 0)
    ).filter(
        MetricSnapshot.metric_key == metric_key,
        MetricSnapshot.period_start >= period.start,
        MetricSnapshot.period_start < period.end,
    ).scalar() or 0
    return float(total)


def compute(period) -> dict:
    # Articles vendus en boutique (quantités des lignes POS).
    pos_items = db.session.query(
        db.func.coalesce(db.func.sum(OrderLine.qty), 0)
    ).join(Order, Order.id == OrderLine.order_id).filter(
        Order.date_order >= period.start,
        Order.date_order < period.end,
        Order.state.in_(POS_REVENUE_STATES),
    ).scalar() or 0

    vinted_items = _manual_sum(period, "vinted.items_sold")
    donated = _manual_sum(period, "env.items_donated")
    collected = _manual_sum(period, "env.items_collected")

    items_reused = float(pos_items) + vinted_items + donated

    weight_kg = items_reused * factor("textile.avg_weight_kg")
    co2e = weight_kg * factor("textile.co2e_per_kg")
    water = weight_kg * factor("textile.water_l_per_kg")
    car_km = co2e * factor("equiv.car_km_per_co2e_kg")
    reuse_rate = (items_reused / collected) if collected > 0 else None

    return {
        "env.items_reused": items_reused,
        "env.weight_kg": weight_kg,
        "env.co2e_avoided_kg": co2e,
        "env.water_saved_l": water,
        "env.reuse_rate": reuse_rate,
        "env.car_km_equiv": car_km,
    }


# --- Paramétrage --------------------------------------------------------------

def ensure_seeded():
    """Crée les facteurs par défaut absents (au 1er accès à la page Facteurs)."""
    created = False
    for key, (unit, value, label, url) in DEFAULT_FACTORS.items():
        if db.session.query(ImpactFactor).filter_by(key=key).first() is None:
            db.session.add(ImpactFactor(
                key=key, value=value, unit=unit,
                source_label=label, source_url=url,
            ))
            created = True
    if created:
        db.session.commit()
