"""Calculette 25 : acomptes de TVA du régime simplifié agricole (lot AG12.a). Règles de `vat_installments`
(lot AG2.c) : montant, dispense, échéancier ; aucune déclaration n'est créée."""
from __future__ import annotations

from datetime import date

from app.services import vat_installments
from app.services.calculators import Context, Input, Result, Spec, euros, pct

SPEC = Spec(
    code="acompte-tva", number="25", title="Acomptes de TVA du RSA", category="vat",
    summary="Montant et échéances des acomptes de TVA du régime simplifié agricole, d'après la TVA due l'année "
            "précédente, et dispense éventuelle.",
    inputs=[
        Input("year", "Année des acomptes", "integer"),
        Input("due", "TVA due l'année précédente", "money", "€", help="Ligne 23 de la CA12A de l'année précédente"),
        Input("assets_vat", "TVA sur immobilisations de l'année précédente", "money", "€", required=False,
              help="Ligne 17 de la CA12A : elle compte pour la dispense, pas pour le montant"),
    ],
    example={"year": "2027", "due": "8400", "assets_vat": "1200"},
    method="Chaque acompte vaut la part réglementaire (20 %) de la TVA due l'année précédente, arrondie à l'euro "
           "supérieur ; un acompte par trimestre civil, dû à la date du calendrier réglementaire qui suit, reportée au "
           "jour ouvré. Dispense si la TVA due avant déduction de la TVA sur immobilisations est sous le seuil. "
           "Limites : année civile (l'option pour l'exercice, CA12AE, décale les trimestres) ; un nouvel assujetti "
           "verse au moins 70 % de la TVA réelle du trimestre (CGI art. 1693 bis II) ; la modulation à la baisse "
           "expose à l'intérêt de retard et à la majoration si l'écart dépasse la tolérance.",
    params=("vat.rsa.installment_share_bp", "vat.rsa.installment_exemption_cents", "vat.rsa.installment_calendar"),
)


def on_date(values: dict) -> date:
    return date(values["year"], 12, 31)


def prefill(ctx: Context) -> dict:
    year = date.today().year
    ref = vat_installments.reference(date(year, 1, 1))
    out = {"year": {"value": str(year), "origin": "année en cours"}}
    if ref["source"] != "missing":
        origin = f"CA12A {ref['label']}" if ref["source"] == "ca12a" else "TVA de référence saisie sur l'exercice"
        out["due"] = {"value": f"{ref['due_cents'] / 100:.2f}", "origin": origin}
        out["assets_vat"] = {"value": f"{(ref['assets_cents'] or 0) / 100:.2f}", "origin": origin}
    return out


def compute(values: dict, on: date) -> Result:
    from app.services import reg_params
    year, due, assets_vat = values["year"], values["due"], values["assets_vat"] or 0
    exemption = reg_params.value("vat.rsa.installment_exemption_cents", on)
    share = reg_params.value("vat.rsa.installment_share_bp", on)
    before = due + assets_vat
    details = [("TVA due l'année précédente", euros(due)), ("TVA sur immobilisations", euros(assets_vat)),
               ("TVA avant déduction des immobilisations", euros(before)), ("Seuil de dispense", euros(exemption))]
    if before < exemption:
        return Result(headline=[("Acomptes", "dispense"), ("Total", euros(0))], details=details,
                      warnings=["TVA due avant déduction de la TVA sur immobilisations sous le seuil : pas d'acompte, "
                                "la TVA de l'année se paie avec la CA12A."],
                      actions=[("Déclarations de TVA", "/vat-returns/")])
    amount = vat_installments.proposed_amount(due, on)
    blocks = vat_installments.blocks(date(year, 1, 1), date(year, 12, 31))
    rows = [[n, vat_installments.block_label(s, e), f"{vat_installments.due_date(e):%d/%m/%Y}", euros(amount)]
            for n, (s, e) in enumerate(blocks, start=1)]
    details.append(("Part de chaque acompte", pct(share)))
    warnings = []
    if due == 0:
        warnings.append("Aucune TVA due l'an dernier (crédit ou nouvel assujetti) : vérifiez le cas du nouvel assujetti.")
    return Result(headline=[("Chaque acompte", euros(amount)), ("Total des acomptes", euros(amount * len(blocks)))],
                  details=details, table={"columns": ["N°", "Période", "Échéance", "Montant"], "rows": rows},
                  warnings=warnings, actions=[("Déclarations de TVA", "/vat-returns/")])
