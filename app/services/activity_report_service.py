"""Assemblage du rapport d'activité.

Réunit, pour un exercice comptable :
- les **chiffres live** (adhérents, bénévoles, ventes, visibilité) via
  `dashboard_service` (réutilisé sur la période de l'exercice) ;
- les **blocs narratifs éditables** (`ReportContent`) ;
- (phases ultérieures) l'impact éco-organismes et le bilan financier.

Retourne une `ReportView` = liste ordonnée de sections prête pour le template.
"""
import unicodedata
from dataclasses import dataclass, field

from app.models import ReportContent, EcoDeclaration, ReportAsset
from app.services import dashboard_service
from app.services.eco_declaration_import import FINANCING_MATERIAL


# Catalogue des blocs narratifs : (clé, libellé éditeur).
NARRATIVE_BLOCKS = [
    ("cover_subtitle", "Sous-titre de couverture"),
    ("edito", "Édito / Avant-propos"),
    ("rapport_moral", "Rapport moral"),
    ("gouvernance", "Gouvernance"),
    ("intro_vie_associative", "Intro — Vie associative"),
    ("intro_reemploi", "Intro — Réemploi & impact"),
    ("intro_boutique", "Intro — Boutique & ventes"),
    ("intro_communication", "Intro — Communication & visibilité"),
    ("partenaires", "Partenaires & coopération"),
    ("commentaire_financier", "Commentaire — Bilan financier"),
    ("frise", "Frise historique (HTML — voir aide)"),
    ("perspectives", "Perspectives"),
]
NARRATIVE_LABELS = dict(NARRATIVE_BLOCKS)

# Structure ordonnée des sections du rapport.
# `dimensions` = dimensions du dashboard dont on tire les KPI (phase 2).
SECTIONS = [
    {"key": "edito", "number": 1, "title": "Édito", "blocks": ["edito"]},
    {"key": "rapport_moral", "number": 2, "title": "Rapport moral", "blocks": ["rapport_moral"]},
    {"key": "gouvernance", "number": 3, "title": "Gouvernance", "blocks": ["gouvernance"]},
    {"key": "vie_associative", "number": 4, "title": "Vie associative",
     "blocks": ["intro_vie_associative"], "dimensions": ["social"]},
    {"key": "reemploi", "number": 5, "title": "Réemploi & impact",
     "blocks": ["intro_reemploi"]},
    {"key": "boutique", "number": 6, "title": "Boutique & ventes",
     "blocks": ["intro_boutique"], "dimensions": ["economic"]},
    {"key": "communication", "number": 7, "title": "Communication & visibilité",
     "blocks": ["intro_communication"], "dimensions": ["visibility"]},
    {"key": "partenaires", "number": 8, "title": "Partenaires & coopération",
     "blocks": ["partenaires"]},
    {"key": "financier", "number": 9, "title": "Bilan financier",
     "blocks": ["commentaire_financier"]},
    {"key": "perspectives", "number": 10, "title": "Perspectives",
     "blocks": ["frise", "perspectives"]},
]


@dataclass
class Section:
    key: str
    number: int
    title: str
    narrative: list = field(default_factory=list)   # [{title, body_html}]
    kpis: list = field(default_factory=list)         # [Kpi]
    charts: list = field(default_factory=list)        # [chart_id]
    eco: dict = None                                  # données impact éco (section réemploi)
    financial: dict = None                            # synthèse financière (section bilan)
    photo: object = None                              # ReportAsset illustrant la section


@dataclass
class ReportView:
    fiscal_year: object
    period: object
    cover: dict
    sections: list
    charts: dict = field(default_factory=dict)   # chart_id -> options ECharts
    prorata: bool = False                         # mode de répartition des trimestres éco


def _contents_for(fy):
    return {
        c.block_key: c
        for c in ReportContent.query.filter_by(fiscal_year_id=fy.id).all()
    }


def _narrative(section, contents):
    blocks = []
    for key in section.get("blocks", []):
        c = contents.get(key)
        if c is not None and (c.body_html or "").strip():
            blocks.append({"title": c.title, "body_html": c.body_html})
    return blocks


GREEN = "#1c7a33"
RED = "#c2452d"

# Quels graphes attacher à quelles sections.
SECTION_CHARTS = {
    "vie_associative": ["chart-adherents"],
    "boutique": ["chart-ca"],
}


def _months_in(period):
    """Liste des 1ers jours de mois couverts par la période [start, end)."""
    from datetime import date
    months = []
    cur = date(period.start.year, period.start.month, 1)
    while cur < period.end:
        months.append(cur)
        cur = date(cur.year + 1, 1, 1) if cur.month == 12 else date(cur.year, cur.month + 1, 1)
    return months


def _kpi_value(view, key):
    for kpis in view.sections.values():
        for k in kpis:
            if k.key == key:
                return k.value
    return None


def _bar_line_option(labels, values, kind="bar", color=GREEN, area=False):
    series = {"type": kind, "data": values, "itemStyle": {"color": color}}
    if kind == "line":
        series.update({"smooth": True, "symbol": "circle", "symbolSize": 6,
                       "lineStyle": {"color": color}})
        if area:
            series["areaStyle"] = {"opacity": 0.12, "color": color}
    return {
        "tooltip": {"trigger": "axis"},
        "grid": {"left": 55, "right": 20, "top": 24, "bottom": 40},
        "xAxis": {"type": "category", "data": labels,
                  "axisLine": {"lineStyle": {"color": "#cdbf9f"}}},
        "yAxis": {"type": "value", "splitLine": {"lineStyle": {"color": "#e7dcc4"}}},
        "series": [series],
    }


def _charts(period, view):
    charts = {}

    # Évolution : nouveaux adhérents par mois sur l'exercice.
    from app.services import metrics_aggregator
    months = _months_in(period)
    labels = [m.strftime("%m/%Y") for m in months]
    new_members = []
    for m in months:
        mp = dashboard_service.period_from_args(
            {"gran": "month", "month": m.strftime("%Y-%m")}
        )
        new_members.append(metrics_aggregator.social(mp).get("social.new_members", 0))
    charts["chart-adherents"] = _bar_line_option(
        labels, new_members, kind="line", color=GREEN, area=True
    )

    # CA par canal (euros) sur l'exercice.
    def euros(key):
        v = _kpi_value(view, key)
        return round((v or 0) / 100, 2)
    charts["chart-ca"] = _bar_line_option(
        ["Boutique", "Vinted", "Dons", "Adhésions"],
        [euros("econ.pos_revenue_cents"), euros("vinted.revenue_cents"),
         euros("econ.donations_cents"), euros("econ.memberships_cents")],
        kind="bar", color=GREEN,
    )
    return charts


def _material_slug(material):
    s = unicodedata.normalize("NFKD", material).encode("ascii", "ignore").decode()
    return s.strip().lower().replace(" ", "-")


def _quarter_end_excl(start):
    """1er jour du trimestre suivant (borne de fin exclusive)."""
    from datetime import date
    m = start.month + 3
    y = start.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    return date(y, m, 1)


def _fy_weight(period_start, fy, prorata):
    """Poids d'un trimestre éco dans l'exercice.

    - **indivisible** (défaut) : 1 si `period_start` ∈ [début, fin], sinon 0
      (le trimestre est rattaché par sa date de début, décision design §0) ;
    - **pro-rata** : fraction des jours du trimestre inclus dans l'exercice
      (un trimestre à cheval est réparti entre N-1 et N)."""
    if not prorata:
        return 1.0 if fy.start_date <= period_start <= fy.end_date else 0.0
    from datetime import timedelta
    q_start = period_start
    q_end = _quarter_end_excl(period_start)          # exclusif
    fy_end_excl = fy.end_date + timedelta(days=1)     # exclusif
    lo = max(q_start, fy.start_date)
    hi = min(q_end, fy_end_excl)
    overlap = (hi - lo).days
    if overlap <= 0:
        return 0.0
    return overlap / (q_end - q_start).days


def eco_impact(fy, prorata=None):
    """Agrège les tonnages éco-organismes sur l'exercice. CO₂ = Σ sortant × facteur matière.

    `prorata` : None → valeur de `current_app.config["ECO_PRORATA"]` (défaut False,
    rattachement indivisible). True/False force le mode. Cf. `_fy_weight`."""
    from app.services import impact_engine

    if prorata is None:
        from flask import current_app
        prorata = bool(current_app.config.get("ECO_PRORATA", False))

    rows = EcoDeclaration.query.all()
    collecte = reemploye = 0.0
    financing = 0
    co2 = 0.0
    by_material = {}
    counted = False
    for r in rows:
        w = _fy_weight(r.period_start, fy, prorata)
        if w == 0:
            continue
        if r.material == FINANCING_MATERIAL:
            financing += int(round(r.financing_cents * w))
            continue
        counted = True
        e, s = float(r.entrant_t) * w, float(r.sortant_t) * w
        collecte += e
        reemploye += s
        bm = by_material.setdefault(r.material, {"entrant": 0.0, "sortant": 0.0})
        bm["entrant"] += e
        bm["sortant"] += s
        co2 += s * impact_engine.factor(
            f"reemploi.{_material_slug(r.material)}.co2e_per_t", 0
        )
    reuse_rate = (reemploye / collecte) if collecte else None
    car_km = co2 * impact_engine.factor("equiv.car_km_per_co2e_kg")
    return {
        "has_data": counted,
        "prorata": prorata,
        "collecte_t": round(collecte, 3),
        "reemploye_t": round(reemploye, 3),
        "reuse_rate": reuse_rate,
        "co2e_avoided_kg": round(co2, 1),
        "car_km": round(car_km, 0),
        "financing_cents": financing,
        "by_material": sorted(
            [{"material": m, **v} for m, v in by_material.items()],
            key=lambda x: x["material"],
        ),
    }


def _tonnage_chart(eco):
    materials = [d["material"] for d in eco["by_material"]]
    return {
        "tooltip": {"trigger": "axis"},
        "legend": {"data": ["Collecté", "Réemployé"], "top": 0},
        "grid": {"left": 55, "right": 20, "top": 30, "bottom": 40},
        "xAxis": {"type": "category", "data": materials,
                  "axisLine": {"lineStyle": {"color": "#cdbf9f"}}},
        "yAxis": {"type": "value", "name": "tonnes",
                  "splitLine": {"lineStyle": {"color": "#e7dcc4"}}},
        "series": [
            {"name": "Collecté", "type": "bar",
             "data": [round(d["entrant"], 3) for d in eco["by_material"]],
             "itemStyle": {"color": "#5b5446"}},
            {"name": "Réemployé", "type": "bar",
             "data": [round(d["sortant"], 3) for d in eco["by_material"]],
             "itemStyle": {"color": GREEN}},
        ],
    }


def _previous_fiscal_year(fy):
    from app.models import FiscalYear
    return (
        FiscalYear.query
        .filter(FiscalYear.start_date < fy.start_date)
        .order_by(FiscalYear.start_date.desc())
        .first()
    )


def financial_summary(fy, eco=None):
    """Synthèse financière de l'exercice (compte de résultat agrégé) + N-1.

    Calcule les totaux à partir des **préfixes de classe à 2 chiffres** (disjoints :
    chaque compte n'appartient qu'à une classe), ce qui évite le double comptage des
    lignes de présentation du PCA qui se recouvrent par préfixe (ex. 60 ⊃ 607).
    Montants en centimes.
    """
    from app.services.reports import _net_credit, _net

    fy_prev = _previous_fiscal_year(fy)

    # Préfixes de classe disjoints (exploitation / financier / exceptionnel).
    P_EXPL = ["70", "71", "72", "73", "74", "75", "78", "79"]
    P_FIN = ["76"]
    P_EXC = ["77"]
    C_EXPL = ["60", "61", "62", "63", "64", "65", "68"]
    C_FIN = ["66"]
    C_EXC = ["67"]
    C_IMP = ["69"]

    def nc(prefixes, f):
        return _net_credit(prefixes, f.id) if f else 0

    def nd(prefixes, f):
        return _net(prefixes, f.id) if f else 0

    def both(fn, prefixes):
        return fn(prefixes, fy), fn(prefixes, fy_prev) if fy_prev else 0

    pe = both(nc, P_EXPL)
    ce = both(nd, C_EXPL)
    pf = both(nc, P_FIN)
    cf = both(nd, C_FIN)
    pex = both(nc, P_EXC)
    cex = both(nd, C_EXC)
    imp = both(nd, C_IMP)

    def pair(a, b):
        return (a[0] - b[0], a[1] - b[1])

    res_expl = pair(pe, ce)
    res_fin = pair(pf, cf)
    res_exc = pair(pex, cex)
    res_net = (
        res_expl[0] + res_fin[0] + res_exc[0] - imp[0],
        res_expl[1] + res_fin[1] + res_exc[1] - imp[1],
    )
    benevolat = (nc(["875"], fy), nc(["875"], fy_prev) if fy_prev else 0)

    lines = [
        {"label": "Produits d'exploitation", "n": pe[0], "prev": pe[1], "kind": "normal"},
        {"label": "Charges d'exploitation", "n": ce[0], "prev": ce[1], "kind": "normal"},
        {"label": "Résultat d'exploitation", "n": res_expl[0], "prev": res_expl[1], "kind": "subtotal"},
    ]
    if pf[0] or cf[0] or pf[1] or cf[1]:
        lines.append({"label": "Résultat financier", "n": res_fin[0], "prev": res_fin[1], "kind": "normal"})
    if pex[0] or cex[0] or pex[1] or cex[1]:
        lines.append({"label": "Résultat exceptionnel", "n": res_exc[0], "prev": res_exc[1], "kind": "normal"})
    lines.append({"label": "Résultat de l'exercice", "n": res_net[0], "prev": res_net[1], "kind": "result"})

    memos = []
    if eco and eco.get("financing_cents"):
        memos.append({"label": "dont financement éco-organismes", "n": eco["financing_cents"]})
    if benevolat[0]:
        memos.append({"label": "Bénévolat valorisé (contributions en nature)", "n": benevolat[0]})

    return {
        "has_prev": fy_prev is not None,
        "prev_label": fy_prev.label if fy_prev else None,
        "lines": lines,
        "memos": memos,
        "result_net_cents": res_net[0],
    }


def _live_kpis_by_dimension(period):
    """KPI live par dimension, réutilisant le dashboard Visibilité & Impact."""
    try:
        view = dashboard_service.build_dashboard(period)
        return view.sections, view
    except Exception:
        return {}, None


def build_report(fy, prorata=None) -> ReportView:
    period = dashboard_service.period_for_fiscal_year(fy)
    contents = _contents_for(fy)
    kpis_by_dim, dash_view = _live_kpis_by_dimension(period)

    charts = _charts(period, dash_view) if dash_view is not None else {}

    eco = eco_impact(fy, prorata=prorata)
    if eco["has_data"]:
        charts["chart-tonnages"] = _tonnage_chart(eco)

    assets = {a.slot: a for a in ReportAsset.query.filter_by(fiscal_year_id=fy.id).all()}

    sections = []
    for s in SECTIONS:
        kpis = []
        for dim in s.get("dimensions", []):
            kpis.extend(kpis_by_dim.get(dim, []))
        sec = Section(
            key=s["key"], number=s["number"], title=s["title"],
            narrative=_narrative(s, contents), kpis=kpis,
            photo=assets.get(f"section_{s['key']}"),
        )
        chart_ids = list(SECTION_CHARTS.get(s["key"], []))
        if s["key"] == "reemploi":
            sec.eco = eco
            if "chart-tonnages" in charts:
                chart_ids.append("chart-tonnages")
        if s["key"] == "financier":
            try:
                sec.financial = financial_summary(fy, eco)
            except Exception:
                sec.financial = None
        sec.charts = [cid for cid in chart_ids if cid in charts]
        sections.append(sec)

    cover = {
        "title": "Rapport d'activité",
        "subtitle": (contents.get("cover_subtitle").body_html
                     if contents.get("cover_subtitle") else None),
        "year_label": fy.label,
        "photo_asset": assets.get("cover"),
    }
    return ReportView(fiscal_year=fy, period=period, cover=cover,
                      sections=sections, charts=charts, prorata=eco["prorata"])
