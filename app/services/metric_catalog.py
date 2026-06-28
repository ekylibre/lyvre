"""Registre déclaratif des métriques du dashboard « Visibilité & Impact ».

Source unique de vérité pilotant l'affichage, le stockage, les unités et le sens
(hausse = bien ?) de chaque indicateur. Consommé par `dashboard_service`,
le formulaire de saisie manuelle et l'export.

Champs d'une métrique :
- key        : identifiant unique (ex. 'ga4.active_users')
- label      : libellé affiché
- dimension  : 'visibility' | 'environmental' | 'social' | 'economic'
- source     : 'ga4' | 'facebook_page' | 'facebook_group' | 'vinted'
               | 'internal' | 'computed'
- origin     : 'live' (recalculé) | 'snapshot' (API stockée) | 'manual' (saisie)
- unit       : 'count' | 'cents' | 'kg' | 'co2e_kg' | 'liters' | 'ratio'
               | 'hours' | 'seconds'
- fmt        : 'int' | 'euros' | 'decimal' | 'percent' | 'duration'
- higher_is_better : sens de la variation pour la coloration
- aggregation: 'sum' (flux, cumulable) | 'last' (stock, on prend la dernière valeur)
               — utilisé quand une période couvre plusieurs mois.
"""
from dataclasses import dataclass


DIMENSIONS = [
    ("visibility", "Visibilité & notoriété"),
    ("environmental", "Impact environnemental"),
    ("social", "Impact social"),
    ("economic", "Économique"),
]
DIMENSION_LABELS = dict(DIMENSIONS)


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    dimension: str
    source: str
    origin: str
    unit: str
    fmt: str
    higher_is_better: bool = True
    aggregation: str = "sum"


METRICS = [
    # --- Visibilité -------------------------------------------------------
    Metric("ga4.active_users", "Utilisateurs actifs", "visibility", "ga4",
           "snapshot", "count", "int", aggregation="sum"),
    Metric("ga4.sessions", "Sessions", "visibility", "ga4",
           "snapshot", "count", "int", aggregation="sum"),
    Metric("ga4.screen_page_views", "Pages vues", "visibility", "ga4",
           "snapshot", "count", "int", aggregation="sum"),
    Metric("ga4.engagement_rate", "Taux d'engagement", "visibility", "ga4",
           "snapshot", "ratio", "percent", aggregation="last"),
    Metric("ga4.avg_session_duration", "Durée moy. session", "visibility", "ga4",
           "snapshot", "seconds", "duration", aggregation="last"),
    Metric("facebook_page.followers", "Abonnés Facebook", "visibility",
           "facebook_page", "snapshot", "count", "int", aggregation="last"),
    Metric("facebook_group.members", "Membres du groupe FB", "visibility",
           "facebook_group", "manual", "count", "int", aggregation="last"),
    Metric("vinted.followers", "Abonnés Vinted", "visibility", "vinted",
           "manual", "count", "int", aggregation="last"),
    Metric("vinted.items_listed", "Articles en vente (Vinted)", "visibility",
           "vinted", "manual", "count", "int", aggregation="last"),

    # --- Économique -------------------------------------------------------
    Metric("econ.pos_revenue_cents", "CA boutique (POS)", "economic", "internal",
           "live", "cents", "euros", aggregation="sum"),
    Metric("vinted.revenue_cents", "CA Vinted", "economic", "vinted",
           "manual", "cents", "euros", aggregation="sum"),
    Metric("vinted.items_sold", "Articles vendus (Vinted)", "economic", "vinted",
           "manual", "count", "int", aggregation="sum"),
    Metric("econ.donations_cents", "Dons (HelloAsso)", "economic", "internal",
           "live", "cents", "euros", aggregation="sum"),
    Metric("econ.memberships_cents", "Adhésions (HelloAsso)", "economic",
           "internal", "live", "cents", "euros", aggregation="sum"),

    # --- Social -----------------------------------------------------------
    Metric("social.active_volunteers", "Bénévoles actifs", "social", "internal",
           "live", "count", "int", aggregation="last"),
    Metric("social.volunteer_hours", "Heures de bénévolat", "social", "internal",
           "live", "hours", "decimal", aggregation="sum"),
    Metric("social.volunteer_value_cents", "Bénévolat valorisé", "social",
           "internal", "live", "cents", "euros", aggregation="sum"),
    Metric("social.new_members", "Nouveaux adhérents", "social", "internal",
           "live", "count", "int", aggregation="sum"),
    Metric("social.members_count", "Adhérents (total)", "social", "internal",
           "live", "count", "int", aggregation="last"),
    Metric("social.renewal_rate", "Taux d'adhésions à jour", "social", "internal",
           "live", "ratio", "percent", aggregation="last"),

    # --- Environnemental (déclarations éco-organismes, cf. EcoDeclaration) -
    # Dérivés des tonnages déclarés (import /rapport-activite/eco) :
    Metric("env.collected_kg", "Collecté", "environmental", "computed",
           "live", "kg", "decimal", aggregation="sum"),
    Metric("env.weight_kg", "Réemployé (détourné du déchet)", "environmental",
           "computed", "live", "kg", "decimal", aggregation="sum"),
    Metric("env.co2e_avoided_kg", "CO₂ évité", "environmental", "computed",
           "live", "co2e_kg", "decimal", aggregation="sum"),
    Metric("env.reuse_rate", "Taux de réemploi", "environmental", "computed",
           "live", "ratio", "percent", aggregation="last"),
    Metric("env.car_km_equiv", "Équivalent km voiture évités", "environmental",
           "computed", "live", "decimal", "decimal", aggregation="sum"),
]

# Index par clé + garde-fou contre les doublons de clé.
BY_KEY = {}
for _m in METRICS:
    if _m.key in BY_KEY:
        raise ValueError(f"Clé de métrique dupliquée dans le catalogue : {_m.key}")
    BY_KEY[_m.key] = _m


def get(key):
    return BY_KEY.get(key)


def by_dimension(dimension):
    return [m for m in METRICS if m.dimension == dimension]


def manual_metrics():
    """Métriques à saisir à la main (Vinted, groupe Facebook)."""
    return [m for m in METRICS if m.origin == "manual"]


def snapshot_metrics():
    """Métriques stockées (API externes + manuelles) → lues dans metric_snapshots."""
    return [m for m in METRICS if m.origin in ("snapshot", "manual")]
