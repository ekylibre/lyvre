"""Soldes intermédiaires de gestion pour tous les référentiels (lot NV3, claudedocs/design_navigation.md § 4, Q5).

- Exploitation agricole : présentation agricole (`agri_reports.sig`, art. 73 du CGI pour la valeur ajoutée).
- Autres référentiels : tableau usuel du « système développé » du PCG de 1982, que le PCG 2026 ne reprend plus,
  calculé sur les comptes de classes 6 et 7. Pour une association, les cotisations, dons, legs et mécénat (753 à 756)
  sont montrés à part, après la valeur ajoutée, et entrent dans l'excédent brut (D-NV1).
Les résultats d'exploitation, courant, exceptionnel et net viennent du compte de résultat du référentiel.
"""
from __future__ import annotations

from app.models import FiscalYear
from app.services import agri_reports
from app.services.reports import _amount, _sum_opt, build_compte_resultat

METHOD = ("Tableau usuel des soldes intermédiaires de gestion (système développé du PCG de 1982, que le PCG en vigueur "
          "ne reprend plus), calculé sur les comptes de classes 6 et 7.")

MERCHANDISE = (["707", "7097"], [])
# (clé, libellé, termes) ; un terme : (signe, mode, comptes, exclus) ou (signe, "=", clé d'un solde déjà calculé).
PCG_SIG = [
    ("ventes_marchandises", "Ventes de marchandises", [(+1, "credit", *MERCHANDISE)]),
    ("cout_marchandises", "Coût d'achat des marchandises vendues", [(+1, "debit", ["607", "6087", "6097", "6037"], [])]),
    ("marge_commerciale", "Marge commerciale", [(+1, "=", "ventes_marchandises"), (-1, "=", "cout_marchandises")]),
    ("production_vendue", "Production vendue", [(+1, "credit", ["70"], ["707", "7097"])]),
    ("production_stockee", "Production stockée", [(+1, "credit", ["71"], [])]),
    ("production_immobilisee", "Production immobilisée", [(+1, "credit", ["72"], [])]),
    ("production", "Production de l'exercice", [(+1, "=", "production_vendue"), (+1, "=", "production_stockee"),
                                                (+1, "=", "production_immobilisee")]),
    ("consommations", "Consommations en provenance de tiers", [
        (+1, "debit", ["60", "61", "62"], ["607", "6087", "6097", "6037"])]),
    ("valeur_ajoutee", "Valeur ajoutée", [(+1, "=", "marge_commerciale"), (+1, "=", "production"),
                                          (-1, "=", "consommations")]),
    ("subventions", "Subventions d'exploitation", [(+1, "credit", ["74"], [])]),
    ("ressources_associatives", "Cotisations, dons, legs et mécénat", [(+1, "credit", ["753", "754", "755", "756"], [])]),
    ("impots_taxes", "Impôts, taxes et versements assimilés", [(+1, "debit", ["63"], [])]),
    ("charges_personnel", "Charges de personnel", [(+1, "debit", ["64"], [])]),
    ("ebe", "Excédent brut d'exploitation", [(+1, "=", "valeur_ajoutee"), (+1, "=", "subventions"),
                                             (+1, "=", "ressources_associatives"), (-1, "=", "impots_taxes"),
                                             (-1, "=", "charges_personnel")]),
]
TOTALS = {"marge_commerciale", "production", "valeur_ajoutee", "ebe"}


def _pcg(fy: FiscalYear, fy_prev: FiscalYear | None, chart: str) -> list[dict]:
    done: dict[str, tuple] = {}
    rows = []
    for key, label, terms in PCG_SIG:
        if key == "ressources_associatives" and chart != "asso":
            done[key] = (0, 0 if fy_prev else None)
            continue
        n_parts, p_parts = [], []
        for term in terms:
            if term[1] == "=":
                n, p = done[term[2]]
            else:
                sign_, mode, prefixes, exclude = term
                n = _amount(mode, prefixes, fy.id, exclude)
                p = _amount(mode, prefixes, fy_prev.id, exclude) if fy_prev else None
            n_parts.append(term[0] * n)
            p_parts.append(None if p is None else term[0] * p)
        done[key] = (sum(n_parts), _sum_opt(p_parts) if fy_prev else None)
        rows.append({"key": key, "label": label, "kind": "total" if key in TOTALS else "row",
                     "n": done[key][0], "p": done[key][1]})
    return rows + agri_reports.result_rows(build_compte_resultat(fy, fy_prev, chart), fy_prev)


def compute(fy: FiscalYear, fy_prev: FiscalYear | None, chart: str) -> list[dict]:
    if chart == "agri":
        return agri_reports.sig(fy, fy_prev)
    return _pcg(fy, fy_prev, chart)
