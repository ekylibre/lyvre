"""Profils de restauration d'une sauvegarde Ekylibre (lot RE1, claudedocs/design_restauration_ekylibre.md § 2).

Les décisions propres à la reprise de la SCI Chênes Verts (EK2 à EK6) sortent du code et deviennent des options :
- profil `sci-chenes-verts` : comportement de la reprise SCI, inchangé ;
- profil `standard` : réglé d'après la sauvegarde (référentiel, TVA, premier exercice ouvert).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from app.services.ekylibre.data import EkyData, day

CHARTS = ("agri", "sci", "societe", "asso")


@dataclass(frozen=True)
class Profile:
    name: str
    chart: str
    start: date | None = None             # 1er jour repris ; None : 1er jour du premier exercice ouvert
    until: date | None = None             # date limite incluse ; None : fin du dernier exercice
    absorb_purchase_vat: bool = False     # EK3 : TVA déductible des achats intégrée à la charge (non assujetti)
    land_reclass: bool = False            # EK6 : terrains (Bois, Terres) reclassés en 211
    validate_rule: str = "locked_years"   # « confirmed » (EK2) | « locked_years » (Q4)
    sales_states: frozenset = field(default_factory=lambda: frozenset({"invoice", "draft", "estimate"}))
    attachments_from: int | None = None   # SCI : 2026 (achats) ; standard : 1re année reprise (Q8)
    associates_from_cashes: bool = True   # Q9 : comptes courants d'associés → associés sans parts (lot RE3)
    agronomy: frozenset = field(default_factory=lambda: frozenset({"activities", "surfaces", "stock"}))
    copy_access_from: str | None = None
    dedupe_entity_names: bool = True      # Q5 : « nom (ville) », sinon « nom (#n° Ekylibre) »
    notes: tuple = ()                     # raisons des réglages détectés, pour le rapport

    @property
    def is_sci(self) -> bool:
        return self.name == "sci-chenes-verts"

    def should_validate(self, entry: dict, fiscal_year: dict | None) -> bool:
        """Q4 : validée si l'écriture est confirmée, ou (profil standard) si son exercice est verrouillé."""
        if entry.get("state") in ("confirmed", "closed"):
            return True
        return self.validate_rule == "locked_years" and (fiscal_year or {}).get("state") in ("locked", "closed")

    def describe(self) -> list[str]:
        return [f"Profil : **{self.name}**, référentiel `{self.chart}`",
                f"TVA déductible des achats {'intégrée à la charge (EK3)' if self.absorb_purchase_vat else 'conservée en 4456x'}",
                "Écritures validées : " + ("confirmées dans Ekylibre (EK2)" if self.validate_rule == "confirmed"
                                           else "confirmées, ou d'un exercice verrouillé dans Ekylibre (Q4)"),
                *self.notes]


def sci(start: date = date(2025, 1, 1), until: date = date(2026, 6, 30), attachments_from: int | None = 2026,
        copy_access_from: str | None = "chenes-verts") -> Profile:
    """Profil de la reprise de la SCI Chênes Verts (design_import_ekylibre_sci.md), à l'identique."""
    return Profile(name="sci-chenes-verts", chart="sci", start=start, until=until, absorb_purchase_vat=True,
                   land_reclass=True, validate_rule="confirmed", sales_states=frozenset({"invoice", "draft", "estimate", "aborted"}),
                   attachments_from=attachments_from, associates_from_cashes=False, agronomy=frozenset(),
                   copy_access_from=copy_access_from)


def detect_chart(data: EkyData) -> tuple[str, str]:
    """Référentiel d'après les préférences d'Ekylibre (RE-C4) : (référentiel, raison)."""
    system = data.preference("accounting_system") or ""
    position = data.preference("fiscal_position") or ""
    if system.startswith("fr_pcga") or position.startswith("fr_ba"):
        return "agri", f"plan agricole (accounting_system {system or '—'}, fiscal_position {position or '—'})"
    return "societe", f"plan société par défaut (accounting_system {system or '—'})"


def first_open_year(data: EkyData) -> dict | None:
    years = sorted(data.rows["financial_years"], key=lambda fy: fy["started_on"])
    return next((fy for fy in years if fy.get("state") == "opened" and fy.get("closed") != "t"), years[-1] if years else None)


def standard(data: EkyData, chart: str | None = None, start: date | None = None, until: date | None = None,
             all_history: bool = False) -> Profile:
    """Profil `standard` réglé d'après la sauvegarde ; les arguments explicites l'emportent."""
    notes = []
    if chart is None:
        chart, why = detect_chart(data)
        notes.append(f"Référentiel détecté : {why}")
    elif chart not in CHARTS:
        raise ValueError(f"Référentiel inconnu : {chart}")
    company = data.own_company()
    subjected = company is None or company.get("vat_subjected") != "f"
    notes.append("Structure assujettie à la TVA (fiche de la structure)" if subjected
                 else "Structure non assujettie à la TVA : TVA des achats intégrée à la charge")
    years = sorted(data.rows["financial_years"], key=lambda fy: fy["started_on"])
    if start is None and years:
        first = years[0] if all_history else first_open_year(data)
        start = day(first["started_on"])
        notes.append("Période : tout l'historique" if all_history else
                     f"Période : à partir du premier exercice ouvert dans Ekylibre ({first.get('code') or start.year})")
    if until is None and years:
        until = day(years[-1]["stopped_on"])
    return Profile(name="standard", chart=chart, start=start, until=until, absorb_purchase_vat=not subjected,
                   attachments_from=start.year if start else None, notes=tuple(notes))


def with_period(profile: Profile, start: date | None = None, until: date | None = None) -> Profile:
    return replace(profile, start=start or profile.start, until=until or profile.until)
