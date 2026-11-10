"""Calculette 15 : révision d'un loyer ou d'un fermage selon l'indice (lot AG12.b). Règle de `rent_revision` (lot L5) :
loyer × nouvel indice ÷ indice de référence, au centime ; indices lus dans Lyvre (INSEE ou arrêté saisi)."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.services import rent_revision
from app.services.calculators import CalculatorError, Context, Input, Result, Spec, euros, number

SPEC = Spec(
    code="fermage", number="15", title="Révision d'un fermage ou d'un loyer", category="management",
    summary="Nouveau loyer annuel d'après l'indice des fermages (ou ILC, ILAT, IRL) entre la période de référence "
            "et la période de révision.",
    inputs=[
        Input("rent", "Loyer annuel actuel", "money", "€"),
        Input("index_code", "Indice", "choice", choices=[("FERMAGES", "Indice national des fermages"),
                                                         ("ILC", "ILC"), ("ILAT", "ILAT"), ("IRL", "IRL")],
              default="FERMAGES"),
        Input("old_period", "Période de référence", "text", help="Fermages : année (2025) ; autres : 2025-T2"),
        Input("new_period", "Période de révision", "text"),
        Input("old_value", "Indice de référence", "number", required=False, help="Vide : valeur enregistrée dans Lyvre"),
        Input("new_value", "Nouvel indice", "number", required=False, help="Vide : valeur enregistrée dans Lyvre"),
    ],
    example={"rent": "4800", "index_code": "FERMAGES", "old_period": "2025", "new_period": "2026",
             "old_value": "122.55", "new_value": "123.06"},
    method="Nouveau loyer = loyer actuel × nouvel indice ÷ indice de référence, arrondi au centime (clause d'indexation "
           "du bail, Code rural art. L411-11 pour les fermages). Les indices viennent de Ventes › Indices de loyer "
           "(INSEE pour ILC, ILAT, IRL ; arrêté annuel saisi pour les fermages), sauf valeur saisie ici. Limites : le "
           "bail révise chaque ligne séparément, ce qui peut écarter le total d'un centime ; les minima et maxima "
           "préfectoraux du fermage ne sont pas contrôlés.",
    prefill_label="Bail",
)


# Essai de l'interface (10/11/2026) : affiché quand rien n'est à reprendre du dossier.
PREFILL_EMPTY = "aucun bail actif avec un indice de révision (Ventes › Baux et quittances)"

def prefill_options(ctx: Context) -> list[dict]:
    from app.models import Lease
    rows = Lease.query.filter(Lease.status == "active", Lease.index_code.isnot(None)).order_by(Lease.unit_label)
    return [{"value": str(l.id), "label": f"{l.unit_label} — {l.entity.name}"} for l in rows]


def prefill(ctx: Context) -> dict:
    from app.extensions import db
    from app.models import Lease
    from app.services import leases
    lease = db.session.get(Lease, int(ctx.choice)) if (ctx.choice or "").isdigit() else None
    if lease is None or not lease.index_code:
        return {}
    origin = f"bail {lease.unit_label}"
    out = {"rent": {"value": f"{leases.annual_total(lease) / 100:.2f}", "origin": origin},
           "index_code": {"value": lease.index_code, "origin": origin}}
    if lease.index_reference_period:
        new_period = rent_revision.shift_period(lease.index_reference_period, lease.revision_months or 12)
        out["old_period"] = {"value": lease.index_reference_period, "origin": origin}
        out["new_period"] = {"value": new_period, "origin": f"{origin}, révision tous les {lease.revision_months or 12} mois"}
    return out


def compute(values: dict, on: date) -> Result:
    code = values["index_code"]
    try:
        old_period = rent_revision.normalize_period(code, values["old_period"])
        new_period = rent_revision.normalize_period(code, values["new_period"])
    except Exception:  # noqa: BLE001 — format de période invalide
        raise CalculatorError("Période attendue : année (fermages) ou trimestre (2025-T2).", "old_period") from None
    old = values["old_value"] if values["old_value"] is not None else rent_revision.value_of(code, old_period)
    new = values["new_value"] if values["new_value"] is not None else rent_revision.value_of(code, new_period)
    missing = [rent_revision.label_period(p) for p, v in ((old_period, old), (new_period, new)) if v is None]
    if missing:
        raise CalculatorError(f"Indice {code} inconnu pour : {', '.join(missing)} (Ventes › Indices de loyer, ou "
                              "saisissez la valeur).", status=409)
    if Decimal(old) <= 0:
        raise CalculatorError("Indice de référence positif attendu.", "old_value")
    ratio = Decimal(new) / Decimal(old)
    rent = rent_revision.apply_ratio(values["rent"], ratio)
    return Result(headline=[("Nouveau loyer annuel", euros(rent)), ("Variation", euros(rent - values["rent"]))],
                  details=[("Indice de référence", f"{number(old, 2)} ({rent_revision.label_period(old_period)})"),
                           ("Nouvel indice", f"{number(new, 2)} ({rent_revision.label_period(new_period)})"),
                           ("Évolution", f"{number((ratio - 1) * 100, 2)} %")],
                  actions=[("Baux", "/leases/"), ("Indices de loyer", "/rent-indices/")])
