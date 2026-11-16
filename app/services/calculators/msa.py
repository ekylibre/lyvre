"""Calculette 17 : cotisations MSA d'un chef d'exploitation (lot AG12.b). Calcul de `msa_estimate.estimate` (lot AG7.e),
barème NSA daté ; préremplissage par l'assiette retenue de l'historique (AG7)."""
from __future__ import annotations

from datetime import date

from app.services import msa_estimate
from app.services.calculators import Context, CalculatorError, Input, Result, Spec, euros

SPEC = Spec(
    code="msa", number="17", title="Cotisations MSA", category="social",
    summary="Estimation des cotisations et contributions sociales d'un chef d'exploitation, ligne par ligne, sur "
            "une assiette donnée.",
    inputs=[
        Input("year", "Année des cotisations", "integer"),
        Input("base", "Assiette des cotisations", "money", "€", required=False,
              help="Assiette annuelle ou moyenne triennale retenue (sans objet pour le collaborateur)"),
        Input("status", "Statut", "choice", choices=[("principal", "Chef d'exploitation à titre principal"),
                                                     ("secondary", "À titre secondaire"),
                                                     ("collaborator", "Collaborateur d'exploitation"),
                                                     ("solidarity", "Cotisant de solidarité")], default="principal"),
        Input("ja_year", "Exonération jeune agriculteur", "choice", required=False,
              choices=[(str(i), f"{i}e année" if i > 1 else "1re année") for i in range(1, 6)],
              help="Année d'exonération (1 à 5) ; cumulable avec le taux réduit AMEXA"),
        Input("installation", "Nouvel installé sans revenus", "choice", required=False, default="no",
              choices=[("no", "Non"), ("yes", "Oui (assiettes forfaitaires d'installation)")]),
        Input("atexa", "Catégorie ATEXA", "choice", required=False,
              choices=[(c, f"Catégorie {c}") for c in msa_estimate.ATEXA_CATEGORIES], help="Indiquée sur l'avis MSA"),
    ],
    example={"year": "2027", "base": "32000", "status": "principal", "atexa": "B"},
    method="Barème des non-salariés agricoles (NSA) de la MSA : assurance maladie, invalidité, indemnités journalières, "
           "retraite de base plafonnée et déplafonnée, retraite complémentaire, prestations familiales, ATEXA, CSG et "
           "CRDS, VIVEA et FMSE, avec leurs assiettes minimales. Estimation indicative : le montant appelé par la "
           "caisse fait foi ; ni l'exonération jeune agriculteur, ni les cotisations complémentaires, ni les membres "
           "de la famille ne sont comptés.",
    params=("msa.pass_cents", "msa.smic_hour_cents", "msa.csg.deductible_bp", "msa.csg.non_deductible_bp", "msa.crds_bp"),
    prefill_label="Exploitant",
)


def on_date(values: dict) -> date:
    """Barème de l'année de cotisation, sinon le dernier barème connu (même repli que `msa_estimate._params`)."""
    from app.services import reg_params
    wanted = date(values["year"], 1, 1)
    if reg_params.get("msa.amexa.rates", wanted, default=None) is not None:
        return wanted
    latest = max((p.valid_from for p in reg_params.history("msa.amexa.rates")), default=None)
    return latest or wanted


# Essai de l'interface (10/11/2026) : affiché quand rien n'est à reprendre du dossier.
PREFILL_EMPTY = "aucun exploitant (Compta › Fiscal et social › Cotisations MSA)"

def prefill_options(ctx: Context) -> list[dict]:
    from app.models import MsaPerson
    from app.services import msa
    return [{"value": str(p.id), "label": msa.person_name(p)} for p in MsaPerson.query.order_by(MsaPerson.id)]


def prefill(ctx: Context) -> dict:
    from app.extensions import db
    from app.models import MsaBase, MsaPerson
    from app.services import msa
    person = db.session.get(MsaPerson, int(ctx.choice)) if (ctx.choice or "").isdigit() else None
    if person is None:
        return {}
    origin = f"MSA › {msa.person_name(person)}"
    out = {"status": {"value": person.status, "origin": origin}}
    if person.atexa_category:
        out["atexa"] = {"value": person.atexa_category, "origin": origin}
    label = "assiette annuelle" if person.base_option == "annual" else "moyenne triennale"
    last = MsaBase.query.filter_by(person_id=person.id).order_by(MsaBase.year.desc()).first()
    if last is not None:
        comp = msa.comparison(person, last.year, None)
        out["year"] = {"value": str(comp["contribution_year"]), "origin": f"revenus {last.year}"}
        if comp["retained_cents"] is not None:
            out["base"] = {"value": f"{comp['retained_cents'] / 100:.2f}", "origin": f"{label} (historique MSA)"}
        return out
    # Essai de l'interface (10/11/2026) : sans historique enregistré (résultat fiscal non figé), l'assiette calculée
    # par l'écran MSA sur le dernier exercice.
    from app.models import FiscalYear
    fy = FiscalYear.query.order_by(FiscalYear.end_date.desc()).first()
    if fy is None:
        return out
    try:
        data = msa.compute(fy)
    except Exception:  # noqa: BLE001 — préremplissage facultatif
        return out
    item = next((i for i in data["people"] if i["person"]["id"] == person.id), None)
    if item is None or item["base_cents"] is None:
        return out
    comp = msa.comparison(person, data["year"], item["base_cents"], current_income=item["income_cents"])
    out["year"] = {"value": str(comp["contribution_year"]), "origin": f"revenus {data['year']} (exercice {fy.label})"}
    if comp["retained_cents"] is not None:
        out["base"] = {"value": f"{comp['retained_cents'] / 100:.2f}", "origin": f"{label} (écran MSA, exercice {fy.label})"}
    return out


def compute(values: dict, on: date) -> Result:
    installation = values.get("installation") == "yes"
    if values["status"] != "collaborator" and values["base"] is None and not installation:
        raise CalculatorError("Assiette des cotisations (ou revenus pour le cotisant de solidarité) à saisir.", "base")
    ja = int(values["ja_year"]) if values.get("ja_year") else None
    data = msa_estimate.estimate(values["base"], values["year"], values["status"], values["atexa"], installation=installation,
                                 ja_year=ja)
    if not data["available"]:
        raise CalculatorError(data["reason"], status=409)
    t = data["totals"]
    return Result(headline=[("Total estimé", euros(t["total_cents"])), ("dont cotisations", euros(t["contributions_cents"]))],
                  details=[("CSG et CRDS", euros(t["csg_crds_cents"])), ("dont non déductible", euros(t["non_deductible_cents"])),
                           ("VIVEA et FMSE", euros(t["third_party_cents"]))],
                  table={"columns": ["Cotisation", "Calcul", "Montant"],
                         "rows": [[l["label"], l["detail"], euros(l["amount_cents"])] for l in data["lines"]]},
                  warnings=data["warnings"], actions=[("Cotisations MSA", "/msa/")])
