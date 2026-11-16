"""Corpus de l'assistant, en contexte et en cache (lot AG9b.b, claudedocs/design_assistant_agricole.md § 4, Q-C3).

Texte **déterministe** (tri par identifiant, sans date du jour) pour que le préfixe en cache serve à toutes les
conversations : fiches d'échéances (`data/deadlines/*.yml`), paramètres réglementaires datés des fichiers
(`data/regulatory/*.json`, valeurs de référence ; la valeur en vigueur, surcharges comprises, se lit par l'outil
`get_parameter`), fiches de méthode (`data/kb/fiches/agri/`, lot CG4) et carte des écrans de Lyvre.
"""
from __future__ import annotations

import json
from functools import lru_cache

SCREENS = (
    ("/agenda/", "Échéancier (échéances, statuts, paiements)"),
    ("/vat-returns/", "Déclarations de TVA (CA12A, CA3, acomptes)"),
    ("/rfa/", "Remboursement forfaitaire agricole"),
    ("/aids/", "Aides et subventions"),
    ("/inventory/", "Inventaire de clôture (stocks, avances aux cultures, lots d'animaux)"),
    ("/tax-result/", "Résultat fiscal (JA, DEP, 73 A, plus-values, liasse 2139 / 2143)"),
    ("/msa/", "Cotisations MSA (assiette, option, appels, estimation)"),
    ("/activities/", "Activités, campagnes, surfaces et effectifs, clés de répartition"),
    ("/analytic/", "Ventilation analytique"),
    ("/activities/margins", "Marges par activité"),
    ("/entries/", "Écritures (onglets Écritures et Lettrage)"),
    ("/reports/", "Éditions comptables : balance, grand livre, bilan, compte de résultat, soldes intermédiaires de gestion"),
    ("/bank-accounts/", "Comptes bancaires et transactions"),
    ("/documents/", "Documents : fichiers enregistrés (pièces, relevés, décomptes, quittances, FEC), en lecture"),
    ("/assets/", "Immobilisations et biens vivants"),
    ("/configuration/organization/?tab=tax", "Structure › Fiscalité (régimes, options)"),
    ("/configuration/organization/?tab=agri", "Structure › Activités et démarches (profil agricole)"),
)


def _fiche_line(f: dict) -> str:
    applies = json.dumps(f.get("applies"), ensure_ascii=False, sort_keys=True) if f.get("applies") else "toutes"
    events = "; ".join(e.get("label", "") for e in f.get("events") or [])
    links = " ".join(f.get("links") or [])
    parts = [f"[{f['id']}] {f['title']} — {f['organism']} ({f['domain']}), fiabilité {f['reliability']}",
             f"  {f.get('summary', '').strip()}", f"  Applicabilité : {applies}. Événements : {events or 'aucun'}."]
    if f.get("penalties"):
        parts.append(f"  Pénalités : {f['penalties']}")
    if links:
        parts.append(f"  Sources : {links}")
    return "\n".join(parts)


def _param_line(p) -> str:
    period = f"du {p.valid_from.isoformat()}" + (f" au {p.valid_to.isoformat()}" if p.valid_to else "")
    value = json.dumps(p.value, ensure_ascii=False, sort_keys=True)
    note = f" — {p.note}" if p.note else ""
    return f"[{p.key}] = {value} ({period}, fiabilité {p.reliability}) ; source : {p.source_label or p.source}{note}"


@lru_cache(maxsize=1)
def text() -> str:
    from app.services import deadlines, kb, reg_params
    fiches = sorted(deadlines.fiches(), key=lambda f: f["id"])
    params = sorted(reg_params.file_params(), key=lambda p: (p.key, p.valid_from))
    return "\n\n".join([
        "# Corpus Lyvre (référence)",
        "Fiabilité : V vérifiée, R règle stable, A valeur annuelle, I incertaine (à valider avec l'expert-comptable). "
        "Montants des paramètres en centimes (_cents), taux en points de base (_bp : 100 = 1 %).",
        "## Fiches d'échéances\n" + "\n".join(_fiche_line(f) for f in fiches),
        "## Paramètres réglementaires datés (valeurs de référence ; valeur en vigueur : outil get_parameter)\n"
        + "\n".join(_param_line(p) for p in params),
        "## Fiches de méthode (synthèses de Lyvre ; chiffres : paramètres datés cités entre crochets)\n"
        + (kb.corpus_text("agri") or "(aucune)"),
        "## Écrans de Lyvre (pour orienter l'utilisateur)\n" + "\n".join(f"- {route} : {label}" for route, label in SCREENS),
    ])
