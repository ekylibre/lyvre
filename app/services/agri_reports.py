"""États propres à l'exploitation agricole (lot AG1.c, claudedocs/design_compta_agricole.md § 5.3 et § 5.4) :
soldes intermédiaires de gestion et tableau des biens vivants et en-cours (annexe, art. 121-4 du titre 5).

Les soldes se calculent sur les lignes du compte de résultat agricole (``reports.AGRI_CDR_SECTIONS``) : un même
compte n'est jamais lu deux fois. La valeur ajoutée suit la définition de l'art. 73 du CGI (DEP, aléa économique) :
production de l'exercice et marge commerciale moins les consommations en provenance de tiers.
"""
from __future__ import annotations

from app.models import FiscalYear, JournalEntry
from app.services.reports import _amount, _sum_opt, build_compte_resultat, section_total

# Solde → [(signe, section, ligne)] ; « = » : solde déjà calculé (clé), avec son signe.
SIG = [
    ("marge_commerciale", "Marge commerciale", [
        (+1, "produits_exploitation", "ventes_marchandises"), (-1, "charges_exploitation", "achats_marchandises"),
        (-1, "charges_exploitation", "variation_marchandises")]),
    ("production", "Production de l'exercice", [
        (+1, "produits_exploitation", "ventes_animaux"), (+1, "produits_exploitation", "autre_production"),
        (+1, "produits_exploitation", "production_stockee"),
        (+1, "produits_exploitation", "production_immobilisee_vivants"),
        (+1, "produits_exploitation", "production_immobilisee_autres"),
        (+1, "produits_exploitation", "autoconsommation")]),
    ("consommations", "Consommations en provenance de tiers", [
        (+1, "charges_exploitation", "achats_approvisionnements"),
        (+1, "charges_exploitation", "variation_approvisionnements"),
        (+1, "charges_exploitation", "achats_animaux"), (+1, "charges_exploitation", "autres_achats")]),
    ("valeur_ajoutee", "Valeur ajoutée", [(+1, "=", "marge_commerciale"), (+1, "=", "production"),
                                          (-1, "=", "consommations")]),
    ("subventions", "Indemnités et subventions d'exploitation", [(+1, "produits_exploitation", "subventions")]),
    ("impots_taxes", "Impôts, taxes et versements assimilés", [(+1, "charges_exploitation", "impots_taxes")]),
    ("charges_personnel", "Charges de personnel (rémunérations et cotisations)", [
        (+1, "charges_exploitation", "remunerations"), (+1, "charges_exploitation", "cotisations")]),
    ("ebe", "Excédent brut d'exploitation", [(+1, "=", "valeur_ajoutee"), (+1, "=", "subventions"),
                                             (-1, "=", "impots_taxes"), (-1, "=", "charges_personnel")]),
]
# Soldes mis en avant (les autres lignes sont leurs composantes).
TOTALS = {"marge_commerciale", "production", "valeur_ajoutee", "ebe"}


def _value(cdr: dict, sign: int, section: str, key: str, done: dict, index: int):
    source = done[key] if section == "=" else cdr[section][key]
    value = source[index]
    return None if value is None else sign * value


def sig(fy: FiscalYear, fy_prev: FiscalYear | None = None) -> list[dict]:
    """Soldes intermédiaires de gestion, N et N-1 (centimes), puis résultats d'exploitation, courant et net."""
    cdr = build_compte_resultat(fy, fy_prev, "agri")
    done: dict[str, tuple] = {}
    rows = []
    for key, label, terms in SIG:
        n = sum(_value(cdr, *term, done, 0) for term in terms)
        p = _sum_opt([_value(cdr, *term, done, 1) for term in terms]) if fy_prev else None
        done[key] = (n, p)
        rows.append({"key": key, "label": label, "kind": "total" if key in TOTALS else "row", "n": n, "p": p})

    def result(*pairs):
        n = sum(sign * section_total(cdr[section])[0] for sign, section in pairs)
        p = _sum_opt([sign * v for sign, section in pairs if (v := section_total(cdr[section])[1]) is not None]) \
            if fy_prev else None
        return n, p

    operating = result((+1, "produits_exploitation"), (-1, "charges_exploitation"))
    financial = result((+1, "produits_financiers"), (-1, "charges_financieres"))
    exceptional = result((+1, "produits_exceptionnels"), (-1, "charges_exceptionnelles"))
    current = (operating[0] + financial[0], _sum_opt([operating[1], financial[1]]) if fy_prev else None)
    taxes = tuple(a if a is None else a + (b or 0) for a, b in zip(cdr["impots_benefices"], cdr["participation_salaries"]))
    net = (current[0] + exceptional[0] - taxes[0],
           None if not fy_prev or current[1] is None else current[1] + (exceptional[1] or 0) - (taxes[1] or 0))
    for key, label, values in (("resultat_exploitation", "Résultat d'exploitation", operating),
                               ("resultat_courant", "Résultat courant avant impôts", current),
                               ("resultat_exceptionnel", "Résultat exceptionnel", exceptional),
                               ("resultat_net", "Résultat de l'exercice", net)):
        rows.append({"key": key, "label": label, "kind": "result", "n": values[0], "p": values[1]})
    return rows


# Tableau des biens vivants (art. 121-4) : (ligne, libellé, comptes bruts, amortissements et dépréciations).
# Les amortissements et dépréciations ne se répartissent que s'ils sont tenus en sous-comptes (2841…) ; le reste
# des comptes 284 / 294 forme une ligne à part.
LIVING_ASSETS = [
    ("long", "Biens vivants (cycle long)", [
        ("animaux", "Animaux", ["241", "243", "2341", "2343", "3112"], ["2841", "2843", "2941", "2943"]),
        ("vegetaux", "Végétaux", ["246", "247", "2346", "2347", "3114"], ["2846", "2847", "2946", "2947"]),
        ("en_cours", "En-cours", ["3311"], []),
    ]),
    ("court", "Biens vivants (cycle court)", [
        ("animaux", "Animaux", ["3113"], []),
        ("vegetaux", "Végétaux", ["3115"], []),
        ("en_cours", "En-cours", ["3312"], []),
    ]),
]
UNSPLIT_DEPRECIATION = (["284", "294"], ["2841", "2843", "2846", "2847", "2941", "2943", "2946", "2947"])


def _net(fy_id, gross, depreciation, exclude=None) -> int:
    return _amount("debit", gross, fy_id, exclude) + (_amount("debit", depreciation, fy_id) if depreciation else 0)


def _opening(fy: FiscalYear, fy_prev: FiscalYear | None, gross, depreciation, exclude=None) -> int:
    """Valeur nette à l'ouverture : clôture de l'exercice précédent s'il est dans Lyvre, sinon à-nouveaux."""
    if fy_prev is not None:
        return _net(fy_prev.id, gross, depreciation, exclude)
    from app.extensions import db
    from app.models import Account, JournalLine
    from app.models.journal_entry import SOURCE_OPENING
    from app.services.reports import _prefix_filters

    prefixes = list(gross) + list(depreciation)
    if not prefixes:
        return 0
    value = (db.session.query(db.func.coalesce(db.func.sum(JournalLine.debit_cents - JournalLine.credit_cents), 0))
             .join(Account, Account.id == JournalLine.account_id)
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .filter(JournalEntry.fiscal_year_id == fy.id, JournalEntry.source == SOURCE_OPENING)
             .filter(*_prefix_filters(prefixes, exclude)).scalar())
    return value or 0


def living_assets_table(fy: FiscalYear, fy_prev: FiscalYear | None = None) -> dict:
    """Valeurs nettes à l'ouverture et à la clôture, par cycle et par nature ; totaux I (long), II (court)."""
    groups, grand = [], {"opening": 0, "closing": 0}
    for key, label, lines in LIVING_ASSETS:
        rows, total = [], {"opening": 0, "closing": 0}
        for line_key, line_label, gross, depreciation in lines:
            opening = _opening(fy, fy_prev, gross, depreciation)
            closing = _net(fy.id, gross, depreciation)
            rows.append({"key": line_key, "label": line_label, "opening": opening, "closing": closing})
            total["opening"] += opening
            total["closing"] += closing
        if key == "long":
            gross, exclude = UNSPLIT_DEPRECIATION
            opening = _opening(fy, fy_prev, gross, [], exclude)
            closing = _net(fy.id, gross, [], exclude)
            if opening or closing:
                rows.append({"key": "amortissements", "label": "Amortissements et dépréciations non répartis",
                             "opening": opening, "closing": closing})
                total["opening"] += opening
                total["closing"] += closing
        groups.append({"key": key, "label": label, "rows": rows, "total": total})
        grand["opening"] += total["opening"]
        grand["closing"] += total["closing"]
    return {"groups": groups, "total": grand, "headcount": living_headcount(fy)}


def living_headcount(fy: FiscalYear) -> list[dict]:
    """Effectifs des biens vivants immobilisés par nature (lot AG5.d) : clôture, entrées et sorties de l'exercice,
    ouverture déduite (clôture − entrées + sorties)."""
    from app.models import Asset, AssetLivingExit
    from app.models.asset import LIVING_KINDS
    from app.services import assets

    rows = {k: {"kind": k, "label": v, "opening": 0, "entries": 0, "exits": 0, "closing": 0} for k, v in LIVING_KINDS.items()}
    for asset in Asset.query.filter(Asset.living_kind.isnot(None)):
        if asset.components or asset.units is None or not assets.is_living(asset.account):
            continue
        kind = (asset.parent.living_kind if asset.parent is not None and asset.parent.living_kind else asset.living_kind)
        row = rows.setdefault(kind, {"kind": kind, "label": kind, "opening": 0, "entries": 0, "exits": 0, "closing": 0})
        exited = asset.status in ("sold", "scrapped") and asset.disposal_date and asset.disposal_date <= fy.end_date
        in_service = asset.in_service_date and asset.in_service_date <= fy.end_date and asset.status != "waiting"
        if in_service and not exited:
            row["closing"] += asset.units
        if asset.in_service_date and fy.start_date <= asset.in_service_date <= fy.end_date and asset.origin != "split":
            row["entries"] += asset.units
    for exit_ in AssetLivingExit.query.filter(AssetLivingExit.on.between(fy.start_date, fy.end_date)):
        kind = exit_.asset.living_kind or "other"
        rows.setdefault(kind, {"kind": kind, "label": kind, "opening": 0, "entries": 0, "exits": 0, "closing": 0})
        rows[kind]["exits"] += exit_.units or 0
    out = []
    for row in rows.values():
        row["opening"] = row["closing"] - row["entries"] + row["exits"]
        if any(row[k] for k in ("opening", "entries", "exits", "closing")):
            out.append(row)
    return out
