"""Création d'une instance « Exploitation agricole » (lot AG1.b, claudedocs/design_compta_agricole.md § 8 et § 9) :
forme juridique, impôt (IR / IS), régime des bénéfices agricoles et premier exercice, saisis en trois étapes et
validés **avant** le provisioning ; puis écrits dans la base de la nouvelle instance. Le SIREN et le régime de TVA,
facultatifs, suivent le même chemin.

Le régime choisit le mode de tenue (C3) : micro-BA → comptabilité simplifiée (recettes et dépenses, exercice civil),
réel simplifié et réel normal → partie double en engagement (AGD10).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from flask import g

from app.services import organization, reg_params
from app.services.tax_profile import COMPANY_FORMS, KINDS, LEGAL_FORMS

# Formes proposées pour une exploitation (ni association, ni SCI).
AGRI_FORMS = ("EI", "EARL", "EARL_U", "GAEC", "SCEA", "GFA", "SARL", "SAS", "SA")
# Sociétés de capitaux : IS de plein droit (l'option IR temporaire n'est pas proposée ici).
IS_ONLY_FORMS = {"SAS", "SA"}


class SetupError(Exception):
    def __init__(self, message, field):
        super().__init__(message)
        self.message, self.field = message, field


@dataclass(frozen=True)
class FarmProfile:
    legal_form_code: str
    income_tax: str
    ba_regime: str | None
    fy_start: date
    fy_end: date
    created_on: date | None
    siren: str | None = None
    vat_regime: str | None = None

    @property
    def bookkeeping(self) -> str:
        return "simple" if self.ba_regime == "micro" else "double"

    @property
    def has_associates(self) -> bool:
        return self.legal_form_code in COMPANY_FORMS


def _date(data, key, label) -> date | None:
    text = str(data.get(key) or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        raise SetupError(f"{label} : date attendue (AAAA-MM-JJ).", key) from None


def parse(data: dict) -> FarmProfile:
    """Profil saisi à la création ; ``SetupError`` rattachée au champ fautif."""
    form = str(data.get("legal_form_code") or "").strip().upper()
    if form not in AGRI_FORMS:
        raise SetupError("Forme juridique de l'exploitation obligatoire.", "legal_form_code")
    income_tax = str(data.get("income_tax") or ("IS" if form in IS_ONLY_FORMS else "IR")).upper()
    if income_tax not in KINDS["income_tax"]["values"]:
        raise SetupError("Impôt : IR ou IS.", "income_tax")
    if form in IS_ONLY_FORMS and income_tax != "IS":
        raise SetupError(f"{LEGAL_FORMS[form]} : impôt sur les sociétés.", "income_tax")
    ba_regime = str(data.get("ba_regime") or "").strip() or None
    if income_tax == "IS":
        ba_regime = None  # une structure à l'IS n'a pas de régime BA
    elif ba_regime not in KINDS["ba_regime"]["values"]:
        raise SetupError("Régime des bénéfices agricoles obligatoire à l'IR.", "ba_regime")
    created_on = _date(data, "created_on", "Date de création")
    start = _date(data, "fy_start", "Début du premier exercice")
    end = _date(data, "fy_end", "Fin du premier exercice")
    if start is None:
        raise SetupError("Début du premier exercice obligatoire.", "fy_start")
    if end is None:
        raise SetupError("Date de clôture du premier exercice obligatoire.", "fy_end")
    if end <= start:
        raise SetupError("La clôture doit suivre le début de l'exercice.", "fy_end")
    if (end - start).days > 730:
        raise SetupError("Un exercice dure 24 mois au plus.", "fy_end")
    if ba_regime == "micro":
        if (start.month, start.day, end.month, end.day) != (1, 1, 12, 31) or start.year != end.year:
            raise SetupError("Micro-BA : l'exercice est l'année civile (du 01/01 au 31/12).", "fy_end")
        if form in COMPANY_FORMS and form != "EARL_U":
            cutoff = reg_params.value("ba.micro.company_cutoff_date", start, default=None)
            if created_on is None:
                raise SetupError("Micro-BA d'une société : date de création obligatoire (CGI art. 69 D).", "created_on")
            if cutoff and created_on >= date.fromisoformat(cutoff):
                raise SetupError("Micro-BA interdit : société créée depuis le 01/01/1997 (CGI art. 69 D), sauf EARL "
                                 "unipersonnelle.", "ba_regime")
    siren = None
    if str(data.get("siren") or "").strip():
        clean, errors = organization.validate({"siren": data["siren"]})
        if errors:
            raise SetupError(errors["siren"], "siren")
        siren = clean["siren"]
    vat_regime = str(data.get("vat_regime") or "").strip() or None
    if vat_regime and vat_regime not in KINDS["vat_regime"]["values"]:
        raise SetupError("Régime de TVA inconnu.", "vat_regime")
    return FarmProfile(form, income_tax, ba_regime, start, end, created_on, siren, vat_regime)


def fiscal_year_label(start: date, end: date) -> str:
    return str(start.year) if start.year == end.year else f"{start.year}-{end.year}"


def initialize(inst, profile: FarmProfile) -> None:
    """Écrit le profil dans la base (déjà provisionnée) de ``inst`` : forme, date de création et SIREN, régimes datés
    du début du premier exercice, premier exercice."""
    from app.extensions import db
    from app.models import FiscalYear, TaxProfile
    from app.services import organization
    from app.tenant import get_tenant_engine

    saved = g.get("current_instance"), g.get("tenant_engine")
    try:
        g.current_instance, g.tenant_engine = inst, get_tenant_engine(inst)
        org = organization.get()
        org.legal_form_code, org.created_on = profile.legal_form_code, profile.created_on
        if profile.siren:
            org.siren = profile.siren
        db.session.add(TaxProfile(kind="income_tax", value=profile.income_tax, start_date=profile.fy_start,
                                  origin="law", note="Saisi à la création de l'instance"))
        for kind in ("ba_regime", "vat_regime"):
            if getattr(profile, kind):
                db.session.add(TaxProfile(kind=kind, value=getattr(profile, kind), start_date=profile.fy_start,
                                          origin="law", note="Saisi à la création de l'instance"))
        db.session.add(FiscalYear(label=fiscal_year_label(profile.fy_start, profile.fy_end),
                                  start_date=profile.fy_start, end_date=profile.fy_end))
        db.session.commit()
        if profile.bookkeeping == "double":  # lot AG1.e : catalogue des catégories agricoles (partie double)
            from app.services import agri_catalog
            agri_catalog.seed_catalog()
    except Exception:
        db.session.rollback()
        raise
    finally:
        g.current_instance, g.tenant_engine = saved


def meta() -> dict:
    return {"legal_forms": [{"value": f, "label": LEGAL_FORMS[f]} for f in AGRI_FORMS],
            "is_only_forms": sorted(IS_ONLY_FORMS),
            "income_tax": [{"value": k, "label": v} for k, v in KINDS["income_tax"]["values"].items()],
            "ba_regimes": [{"value": k, "label": v} for k, v in KINDS["ba_regime"]["values"].items()],
            "vat_regimes": [{"value": k, "label": v} for k, v in KINDS["vat_regime"]["values"].items()]}
