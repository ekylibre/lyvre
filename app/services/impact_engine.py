"""Moteur d'impact environnemental (réemploi).

Dérive les indicateurs physiques (kg collectés/réemployés, CO₂ évité, équivalent
km voiture) des tonnages déclarés aux éco-organismes (`EcoDeclaration`, alimentée
par l'import /rapport-activite/eco), via les facteurs matière ADEME paramétrables
(`impact_factors`). Calcul par période (rattachement d'un trimestre par sa date
de début, cohérent avec l'agrégation des `metric_snapshots`).
"""
import unicodedata

from app.extensions import db
from app.models import EcoDeclaration, ImpactFactor

# Ligne « Facturation » des déclarations éco : financement, pas un tonnage.
FINANCING_MATERIAL = "Facturation"


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


def _material_slug(material):
    """Normalise une matière en clé de facteur (« Brico-Jardin » → « brico-jardin »)."""
    s = unicodedata.normalize("NFKD", material).encode("ascii", "ignore").decode()
    return s.strip().lower().replace(" ", "-")


def _eco_tonnages(period):
    """Agrège les déclarations éco dont le trimestre démarre dans la période.

    Retourne (collecte_t, reemploye_t, co2e_kg). CO₂ = Σ sortant × facteur matière,
    même formule que la section « Réemploi & impact » du rapport d'activité."""
    rows = db.session.query(EcoDeclaration).filter(
        EcoDeclaration.period_start >= period.start,
        EcoDeclaration.period_start < period.end,
    ).all()
    collecte = reemploye = co2e = 0.0
    for r in rows:
        if r.material == FINANCING_MATERIAL:
            continue
        entrant, sortant = float(r.entrant_t), float(r.sortant_t)
        collecte += entrant
        reemploye += sortant
        co2e += sortant * factor(f"reemploi.{_material_slug(r.material)}.co2e_per_t", 0)
    return collecte, reemploye, co2e


def compute(period) -> dict:
    """Impact environnemental de la période, dérivé des tonnages éco-organismes
    (table `EcoDeclaration`, alimentée par l'import /rapport-activite/eco).

    Sans déclaration sur la période, renvoie {} (indicateurs affichés « — »)."""
    collecte_t, reemploye_t, co2e = _eco_tonnages(period)
    if collecte_t <= 0 and reemploye_t <= 0:
        return {}

    return {
        "env.collected_kg": collecte_t * 1000.0,
        "env.weight_kg": reemploye_t * 1000.0,
        "env.co2e_avoided_kg": co2e,
        "env.reuse_rate": (reemploye_t / collecte_t) if collecte_t > 0 else None,
        "env.car_km_equiv": co2e * factor("equiv.car_km_per_co2e_kg"),
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
