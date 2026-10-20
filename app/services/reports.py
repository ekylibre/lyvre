"""
Build Bilan and Compte de Résultat structures for each chart of accounts.

- ``asso`` : modèle du plan comptable des associations (XLS de référence).
- ``sci``  : plan comptable général adapté aux SCI (doc/plan-comptable-SCI.pdf).

Each line aggregates account codes by prefix using database sums. The SCI
layouts use disjoint prefixes (with exclusions) so that totals never count
an account twice.
"""
from app.extensions import db
from app.models import Account, JournalLine, JournalEntry


def _prefix_filters(prefixes, exclude=None):
    conditions = [Account.code.like(f"{p}%") for p in prefixes]
    filters = [db.or_(*conditions)]
    for p in exclude or ():
        filters.append(~Account.code.like(f"{p}%"))
    return filters


def _sum_accounts(prefixes, fiscal_year_id, side="debit", exclude=None):
    """Sum debit or credit for all accounts whose code starts with any of the given
    prefixes (and none of the ``exclude`` prefixes)."""
    if not prefixes or not fiscal_year_id:
        return 0
    col = JournalLine.debit_cents if side == "debit" else JournalLine.credit_cents
    result = (
        db.session.query(db.func.coalesce(db.func.sum(col), 0))
        .join(Account, Account.id == JournalLine.account_id)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(JournalEntry.fiscal_year_id == fiscal_year_id)
        .filter(*_prefix_filters(prefixes, exclude))
        .scalar()
    )
    return result or 0


def _net(prefixes, fiscal_year_id, exclude=None):
    """Returns debit - credit (positive = debit balance)."""
    d = _sum_accounts(prefixes, fiscal_year_id, "debit", exclude)
    c = _sum_accounts(prefixes, fiscal_year_id, "credit", exclude)
    return d - c


def _net_credit(prefixes, fiscal_year_id, exclude=None):
    """Returns credit - debit (positive = credit balance)."""
    return -_net(prefixes, fiscal_year_id, exclude)


def _account_nets(prefixes, fiscal_year_id, exclude=None):
    """Debit - credit per account (used to split tiers accounts by balance side)."""
    if not prefixes or not fiscal_year_id:
        return []
    rows = (
        db.session.query(
            db.func.coalesce(db.func.sum(JournalLine.debit_cents), 0)
            - db.func.coalesce(db.func.sum(JournalLine.credit_cents), 0)
        )
        .join(Account, Account.id == JournalLine.account_id)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(JournalEntry.fiscal_year_id == fiscal_year_id)
        .filter(*_prefix_filters(prefixes, exclude))
        .group_by(Account.id)
        .all()
    )
    return [r[0] or 0 for r in rows]


def _amount(mode, prefixes, fiscal_year_id, exclude=None):
    """Amount of a report line according to ``mode``:

    - ``debit``       : debit - credit
    - ``credit``      : credit - debit
    - ``debit_only``  : sum of the accounts with a debit balance
    - ``credit_only`` : sum of the accounts with a credit balance
    """
    if mode == "debit":
        return _net(prefixes, fiscal_year_id, exclude)
    if mode == "credit":
        return _net_credit(prefixes, fiscal_year_id, exclude)
    nets = _account_nets(prefixes, fiscal_year_id, exclude)
    if mode == "debit_only":
        return sum(v for v in nets if v > 0)
    if mode == "credit_only":
        return -sum(v for v in nets if v < 0)
    raise ValueError(f"Mode inconnu : {mode}")


def _sum_opt(values):
    """Sum ignoring None; None if every value is None (no N-1 exercise)."""
    values = [v for v in values if v is not None]
    return sum(values) if values else None


# ---------------------------------------------------------------------------
# BILAN
# ---------------------------------------------------------------------------
#
# A layout is a list of lines per side:
#   ("section", label)
#   ("row", label, prefixes, indent[, mode[, exclude]])
#   ("total", label)            -> sum of every "row" of the side so far
# Default mode: "debit" for the actif, "credit" for the passif.

_TIERS_SPLIT_EXCLUDE = ["461", "466", "476", "477"]

BILAN_LAYOUTS = {
    # Bilan du plan comptable des associations (règlement ANC 2018-06). Les
    # comptes de tiers et de trésorerie sont ventilés selon le sens de leur
    # solde (débiteur → actif, créditeur → passif) ; le résultat inclut les
    # classes 6/7 tant que l'exercice n'est pas soldé dans le compte 12.
    "asso": {
        "actif": [
            ("section", "ACTIF IMMOBILISÉ"),
            ("section", "Immobilisations incorporelles"),
            ("row", "Frais d'établissement", ["201"], 2),
            ("row", "Frais de recherche et développement", ["203"], 2),
            ("row", "Donations temporaires d'usufruit", ["204"], 2),
            ("row", "Concessions, brevets, licences…", ["205"], 2),
            ("row", "Autres immobilisations incorporelles", ["20"], 2, "debit", ["201", "203", "204", "205"]),
            ("row", "Immobilisations incorporelles en cours", ["232", "237"], 2),
            ("section", "Immobilisations corporelles"),
            ("row", "Terrains", ["211", "212"], 2),
            ("row", "Constructions", ["213", "214"], 2),
            ("row", "Installations techniques, matériel…", ["215"], 2),
            ("row", "Autres immobilisations corporelles", ["21", "22"], 2, "debit",
             ["211", "212", "213", "214", "215"]),
            ("row", "Immobilisations corporelles en cours", ["23"], 2, "debit", ["232", "237"]),
            ("row", "Biens reçus par legs ou donations", ["24"], 1),
            ("section", "Immobilisations financières"),
            ("row", "Participations et créances rattachées", ["26"], 2),
            ("row", "Autres titres immobilisés", ["27"], 2, "debit", ["274", "275", "276"]),
            ("row", "Prêts", ["274"], 2),
            ("row", "Autres", ["275", "276"], 2),
            ("row", "Amortissements et dépréciations des immobilisations", ["28", "29"], 1),
            ("section", "ACTIF CIRCULANT"),
            ("row", "Stocks et en-cours", ["3"], 1),
            ("row", "Créances clients, usagers", ["41"], 1, "debit_only"),
            ("row", "Créances reçues par legs ou donations", ["461"], 1),
            ("row", "Autres créances", ["40", "42", "43", "44", "45", "46", "47"], 1, "debit_only",
             _TIERS_SPLIT_EXCLUDE),
            ("row", "Dépréciations des comptes de tiers", ["49"], 1),
            ("row", "Valeurs mobilières de placement", ["50", "59"], 1),
            ("row", "Instruments de trésorerie", ["52"], 1, "debit_only"),
            ("row", "Disponibilités", ["51", "53", "54", "58"], 1, "debit_only"),
            ("row", "Charges constatées d'avance", ["486"], 1),
            ("section", "COMPTES DE RÉGULARISATION"),
            ("row", "Frais d'émission des emprunts et charges à répartir", ["48"], 1, "debit", ["486", "487"]),
            ("row", "Primes de remboursement des emprunts", ["169"], 1),
            ("row", "Écarts de conversion actif", ["476"], 1),
            ("total", "TOTAL ACTIF"),
        ],
        "passif": [
            ("section", "FONDS PROPRES"),
            ("section", "Fonds propres sans droit de reprise"),
            ("row", "Fonds propres statutaires", ["1021", "1022"], 2),
            ("row", "Fonds propres complémentaires", ["102"], 2, "credit", ["1021", "1022"]),
            ("section", "Fonds propres avec droit de reprise"),
            ("row", "Fonds statutaires", ["1032"], 2),
            ("row", "Fonds propres complémentaires", ["103"], 2, "credit", ["1032"]),
            ("row", "Écarts de réévaluation", ["105"], 1),
            ("section", "Réserves"),
            ("row", "Réserves statutaires ou contractuelles", ["1063"], 2),
            ("row", "Réserves pour projet de l'entité", ["10681"], 2),
            ("row", "Autres réserves", ["10"], 2, "credit", ["102", "103", "105", "1063", "10681", "108"]),
            ("row", "Report à nouveau", ["11"], 1),
            ("row", "Excédent ou déficit de l'exercice", ["12", "6", "7"], 1),
            ("row", "Fonds propres consomptibles", ["108"], 1),
            ("row", "Subventions d'investissement", ["13"], 1),
            ("row", "Provisions réglementées", ["14"], 1),
            ("section", "FONDS REPORTÉS ET DÉDIÉS"),
            ("row", "Fonds reportés liés aux legs ou donations", ["191", "192"], 1),
            ("row", "Fonds dédiés", ["19"], 1, "credit", ["191", "192"]),
            ("section", "PROVISIONS"),
            ("row", "Provisions pour risques", ["151"], 1),
            ("row", "Provisions pour charges", ["15"], 1, "credit", ["151"]),
            ("section", "DETTES"),
            ("row", "Emprunts obligataires et assimilés (titres associatifs)", ["161", "163"], 1),
            ("row", "Emprunts établissements de crédit", ["164"], 1),
            ("row", "Concours bancaires courants", ["51", "53", "54", "58"], 1, "credit_only"),
            ("row", "Emprunts et dettes financières diverses", ["16", "17", "18"], 1, "credit",
             ["161", "163", "164", "169"]),
            ("row", "Dettes fournisseurs et comptes rattachés", ["40"], 1, "credit_only", ["404", "405"]),
            ("row", "Dettes des legs ou donations", ["466"], 1),
            ("row", "Dettes sur immobilisations et comptes rattachés", ["404", "405"], 1, "credit_only"),
            ("row", "Dettes fiscales et sociales", ["42", "43", "44"], 1, "credit_only"),
            ("row", "Autres dettes", ["41", "45", "46", "47"], 1, "credit_only", _TIERS_SPLIT_EXCLUDE),
            ("row", "Instruments de trésorerie", ["52"], 1, "credit_only"),
            ("row", "Produits constatés d'avance", ["487"], 1),
            ("row", "Écarts de conversion passif", ["477"], 1),
            ("total", "TOTAL PASSIF"),
        ],
    },
    # Bilan PCG (modèle simplifié) pour une SCI, mêmes principes.
    "sci": {
        "actif": [
            ("row", "Capital souscrit non appelé", ["109"], 1),
            ("section", "ACTIF IMMOBILISÉ"),
            ("row", "Immobilisations incorporelles", ["20", "232", "237"], 1),
            ("row", "Terrains", ["211", "212"], 1),
            ("row", "Constructions", ["213", "214"], 1),
            ("row", "Autres immobilisations corporelles", ["21", "22"], 1, "debit", ["211", "212", "213", "214"]),
            ("row", "Immobilisations corporelles en cours", ["23"], 1, "debit", ["232", "236", "237"]),
            ("row", "Immobilisations financières", ["26", "27", "236"], 1),
            ("row", "Amortissements et dépréciations", ["28", "29"], 1),
            ("section", "ACTIF CIRCULANT"),
            ("row", "Stocks et en-cours", ["3"], 1),
            ("row", "Créances locataires et comptes rattachés", ["41"], 1, "debit_only"),
            ("row", "Associés — comptes débiteurs", ["45"], 1, "debit_only"),
            ("row", "Autres créances", ["40", "42", "43", "44", "46", "47"], 1, "debit_only"),
            ("row", "Dépréciations des comptes de tiers", ["49"], 1),
            ("row", "Valeurs mobilières de placement", ["50", "59"], 1),
            ("row", "Disponibilités", ["51", "52", "53", "54", "58"], 1, "debit_only"),
            ("row", "Charges constatées d'avance", ["486"], 1),
            ("row", "Charges à répartir sur plusieurs exercices", ["48"], 1, "debit", ["486", "487"]),
            ("row", "Primes de remboursement des obligations", ["169"], 1),
            ("total", "TOTAL ACTIF"),
        ],
        "passif": [
            ("section", "CAPITAUX PROPRES"),
            ("row", "Capital social", ["101", "108"], 1),
            ("row", "Primes liées au capital social", ["104"], 1),
            ("row", "Écarts de réévaluation", ["105"], 1),
            ("row", "Réserves", ["10"], 1, "credit", ["101", "104", "105", "108", "109"]),
            ("row", "Report à nouveau", ["11"], 1),
            ("row", "Résultat de l'exercice", ["12", "6", "7"], 1),
            ("row", "Subventions d'investissement", ["13"], 1),
            ("row", "Provisions réglementées", ["14"], 1),
            ("section", "PROVISIONS"),
            ("row", "Provisions pour risques et charges", ["15"], 1),
            ("section", "DETTES"),
            ("row", "Emprunts auprès des établissements de crédit", ["164"], 1),
            ("row", "Concours bancaires courants", ["51", "52", "53", "54", "58"], 1, "credit_only"),
            ("row", "Dépôts de garantie reçus", ["165"], 1),
            ("row", "Autres emprunts et dettes financières", ["16", "17", "18"], 1, "credit",
             ["164", "165", "169"]),
            ("row", "Associés — comptes courants", ["45"], 1, "credit_only"),
            ("row", "Dettes fournisseurs et comptes rattachés", ["40"], 1, "credit_only"),
            ("row", "Dettes fiscales et sociales", ["42", "43", "44"], 1, "credit_only"),
            ("row", "Autres dettes", ["41", "46", "47"], 1, "credit_only"),
            ("row", "Produits constatés d'avance", ["487"], 1),
            ("total", "TOTAL PASSIF"),
        ],
    },
}


def _build_bilan_side(lines, default_mode, fy, fy_prev):
    out = []
    n_rows, p_rows = [], []
    for line in lines:
        kind, label = line[0], line[1]
        if kind == "section":
            out.append({"kind": "section", "label": label})
        elif kind == "row":
            prefixes, indent = line[2], line[3]
            mode = line[4] if len(line) > 4 else default_mode
            exclude = line[5] if len(line) > 5 else None
            n = _amount(mode, prefixes, fy.id, exclude) if fy else 0
            p = _amount(mode, prefixes, fy_prev.id, exclude) if fy_prev else None
            n_rows.append(n)
            p_rows.append(p)
            out.append({"kind": "row", "label": label, "indent": indent, "n": n, "p": p})
        elif kind == "total":
            out.append({"kind": "total", "label": label,
                        "n": sum(n_rows), "p": _sum_opt(p_rows)})
    return out


def build_bilan(fy, fy_prev=None, chart="asso"):
    """Returns ``{"actif": [lines], "passif": [lines]}`` for ``chart``.

    Each line is a dict: ``kind`` (section/row/total), ``label`` and, for
    rows and totals, ``n`` / ``p`` amounts in cents (``p`` is None without N-1).
    """
    layout = BILAN_LAYOUTS.get(chart) or BILAN_LAYOUTS["asso"]
    return {
        "actif": _build_bilan_side(layout["actif"], "debit", fy, fy_prev),
        "passif": _build_bilan_side(layout["passif"], "credit", fy, fy_prev),
    }


# ---------------------------------------------------------------------------
# COMPTE DE RÉSULTAT
# ---------------------------------------------------------------------------

# A section lists (key, label, prefixes, exclude). Prefixes are disjoint
# within a chart and cover every class 6 / 7 account exactly once. Keys
# starting with "dont_" are informative sub-lines, excluded from totals.

# Compte de résultat du plan comptable des associations (modèle XLS).
ASSO_CDR_SECTIONS = [
    ("produits_exploitation", "credit", [
        ("cotisations", "Cotisations", ["756"], []),
        ("ventes_biens", "Ventes de biens", ["701", "702", "703", "707"], []),
        ("dont_ventes_dons_nature", "dont ventes de dons en nature", ["7073"], []),
        ("ventes_prestations", "Ventes de prestations de services", ["70"], ["701", "702", "703", "707"]),
        ("dont_parrainages", "dont parrainages", ["7063"], []),
        ("concours_publics_subventions", "Concours publics et subventions d'exploitation", ["73", "74"], []),
        ("versements_fondateurs_dotation", "Versements des fondateurs / dotation consomptible", ["753"], []),
        ("dons_manuels", "Dons manuels", ["754"], ["7542", "7543"]),
        ("mecenat", "Mécénats", ["7542"], []),
        ("legs_donations", "Legs, donations et assurances-vie", ["7543"], []),
        ("contributions_financieres", "Contributions financières", ["755"], []),
        ("reprises_amort_provisions", "Reprises sur amortissements, dépréciations, provisions et transferts de charges", ["78", "79"], ["786", "787", "789", "796", "797"]),
        ("utilisations_fonds_dedies", "Utilisations des fonds dédiés", ["789"], []),
        ("autres_produits", "Autres produits", ["71", "72", "75"], ["753", "754", "755", "756"]),
    ]),
    ("charges_exploitation", "debit", [
        ("achats_marchandises", "Achats de marchandises", ["607"], []),
        ("variation_stocks", "Variation de stocks", ["603"], []),
        ("autres_achats_charges_externes", "Autres achats et charges externes", ["60", "61", "62"], ["603", "607"]),
        ("aides_financieres", "Aides financières", ["657"], []),
        ("impots_taxes", "Impôts, taxes et versements assimilés", ["63"], []),
        ("salaires_traitements", "Salaires et traitements", ["641", "642"], []),
        ("charges_sociales", "Charges sociales", ["64"], ["641", "642"]),
        ("dotations_amort_depreciations", "Dotations aux amortissements et aux dépréciations", ["68"], ["6815", "686", "687", "689"]),
        ("dotations_provisions", "Dotations aux provisions", ["6815"], []),
        ("reports_fonds_dedies", "Reports en fonds dédiés", ["689"], []),
        ("autres_charges", "Autres charges", ["65"], ["657"]),
    ]),
    ("produits_financiers", "credit", [
        ("de_participations", "De participations", ["761"], []),
        ("autres_valeurs_mobilieres", "D'autres valeurs mobilières et créances de l'actif immobilisé", ["762", "763", "764"], []),
        ("autres_interets", "Autres intérêts et produits assimilés", ["76"], ["761", "762", "763", "764", "766", "767"]),
        ("reprises_provisions", "Reprises sur provisions et transferts de charges", ["786", "796"], []),
        ("differences_positives_change", "Différences positives de change", ["766"], []),
        ("produits_nets_cessions_vmp", "Produits nets sur cessions de VMP", ["767"], []),
    ]),
    ("charges_financieres", "debit", [
        ("dotations_amort", "Dotations aux amortissements, dépréciations et provisions", ["686"], []),
        ("interets_charges", "Intérêts et charges assimilées", ["66"], ["666", "667"]),
        ("differences_negatives_change", "Différences négatives de change", ["666"], []),
        ("charges_nettes_cessions_vmp", "Charges nettes sur cessions de VMP", ["667"], []),
    ]),
    ("produits_exceptionnels", "credit", [
        ("sur_operations_gestion", "Sur opérations de gestion", ["77"], ["775", "777", "778"]),
        ("sur_operations_capital", "Sur opérations en capital", ["775", "777", "778"], []),
        ("reprises_provisions", "Reprises sur provisions et transferts de charges", ["787", "797"], []),
    ]),
    ("charges_exceptionnelles", "debit", [
        ("sur_operations_gestion", "Sur opérations de gestion", ["67"], ["675", "678"]),
        ("sur_operations_capital", "Sur opérations en capital", ["675", "678"], []),
        ("dotations_amort", "Dotations aux amortissements, dépréciations et provisions", ["687"], []),
    ]),
    ("contributions_produits", "credit", [
        ("dons_nature", "Dons en nature", ["870"], []),
        ("prestations_nature", "Prestations en nature", ["871"], []),
        ("benevolat", "Bénévolat", ["875"], []),
    ]),
    ("contributions_charges", "debit", [
        ("secours_nature", "Secours en nature", ["860"], []),
        ("mise_dispo_biens", "Mise à disposition gratuite de biens", ["861"], []),
        ("prestations_nature", "Prestations en nature", ["862"], []),
        ("personnel_benevole", "Personnel bénévole", ["864"], []),
    ]),
]

# Compte de résultat PCG pour une SCI.
SCI_CDR_SECTIONS = [
    ("produits_exploitation", "credit", [
        ("loyers", "Loyers et fermages", ["7083"], []),
        ("charges_refacturees", "Charges refacturées aux locataires", ["7085"], []),
        ("autres_ventes", "Autres ventes et prestations de services", ["70"], ["7083", "7085"]),
        ("subventions", "Subventions d'exploitation (ANAH…)", ["74"], []),
        ("reprises_transferts", "Reprises sur amortissements et provisions, transferts de charges", ["78", "79"], ["786", "787", "796", "797"]),
        ("autres_produits", "Autres produits", ["71", "72", "73", "75"], []),
    ]),
    ("charges_exploitation", "debit", [
        ("achats", "Achats et variation de stocks", ["60"], []),
        ("charges_locatives", "Charges locatives et de copropriété", ["614"], []),
        ("entretien", "Entretien et réparations", ["615"], []),
        ("assurances", "Primes d'assurance", ["616"], []),
        ("honoraires", "Honoraires", ["622"], []),
        ("autres_charges_externes", "Autres charges externes", ["61", "62"], ["614", "615", "616", "622"]),
        ("taxe_fonciere", "Taxe foncière", ["63512"], []),
        ("impots_taxes", "Autres impôts et taxes", ["63"], ["63512"]),
        ("charges_personnel", "Charges de personnel", ["64"], []),
        ("dotations", "Dotations aux amortissements et provisions", ["68"], ["686", "687"]),
        ("autres_charges", "Autres charges de gestion courante", ["65"], []),
    ]),
    ("produits_financiers", "credit", [
        ("produits_financiers", "Produits financiers", ["76"], []),
        ("reprises_transferts", "Reprises sur provisions et transferts de charges", ["786", "796"], []),
    ]),
    ("charges_financieres", "debit", [
        ("interets_emprunts", "Intérêts des emprunts", ["661"], []),
        ("autres_charges_financieres", "Autres charges financières", ["66"], ["661"]),
        ("dotations", "Dotations financières aux amortissements et provisions", ["686"], []),
    ]),
    ("produits_exceptionnels", "credit", [
        ("sur_operations_gestion", "Sur opérations de gestion", ["77"], ["775", "777", "778"]),
        ("sur_operations_capital", "Sur opérations en capital", ["775", "777", "778"], []),
        ("reprises_transferts", "Reprises sur provisions et transferts de charges", ["787", "797"], []),
    ]),
    ("charges_exceptionnelles", "debit", [
        ("sur_operations_gestion", "Sur opérations de gestion", ["67"], ["675", "678"]),
        ("sur_operations_capital", "Sur opérations en capital", ["675", "678"], []),
        ("dotations", "Dotations aux amortissements et provisions", ["687"], []),
    ]),
]
PARTICIPATION = (["691"], [])
IMPOTS_BENEFICES = (["69"], ["691"])

CDR_SECTIONS = {"asso": ASSO_CDR_SECTIONS, "sci": SCI_CDR_SECTIONS}


def _cdr_labels(chart):
    """{section: {line key: label}} pour ``chart``."""
    return {
        section: {key: label for key, label, _p, _e in rows}
        for section, _mode, rows in CDR_SECTIONS[chart]
    }


def _build_compte_resultat(sections, fy, fy_prev=None):
    def pair(mode, prefixes, exclude):
        n = _amount(mode, prefixes, fy.id, exclude) if fy else 0
        p = _amount(mode, prefixes, fy_prev.id, exclude) if fy_prev else None
        return (n, p)

    data = {
        section: {key: pair(mode, prefixes, exclude) for key, _l, prefixes, exclude in rows}
        for section, mode, rows in sections
    }
    data.setdefault("contributions_produits", {})
    data.setdefault("contributions_charges", {})
    data["participation_salaries"] = pair("debit", *PARTICIPATION)
    data["impots_benefices"] = pair("debit", *IMPOTS_BENEFICES)
    return data


def build_compte_resultat(fy, fy_prev=None, chart="asso"):
    """Compte de résultat de ``chart``.

    Same top-level keys for every chart (produits_exploitation,
    charges_exploitation, …, participation_salaries, impots_benefices) so that
    callers such as the dashboard work whatever the chart; each section maps a
    line key to an ``(N, N-1)`` tuple of cents.
    """
    return _build_compte_resultat(CDR_SECTIONS.get(chart) or ASSO_CDR_SECTIONS, fy, fy_prev)


# ---------------------------------------------------------------------------
# Lignes à plat du compte de résultat (HTML, CSV, ODS)
# ---------------------------------------------------------------------------

def section_total(section):
    """(N, N-1) totals of a section dict of (n, p) tuples, "dont_" lines excluded."""
    values = [v for key, v in section.items() if not key.startswith("dont_")]
    return (sum(v[0] for v in values), _sum_opt([v[1] for v in values]))


def _diff(a, b):
    return None if a is None or b is None else a - b


def _add(*values):
    return None if any(v is None for v in values) else sum(values)


def compte_resultat_rows(data, chart="asso"):
    """Yields tuples (kind, label, n_value, p_value).

    kind: 'section' (en-tête de section), 'row' (ligne détail),
          'subhead' (en-tête de sous-groupe sans valeur), 'total' (total intermédiaire),
          'result' (résultat encadré).
    Leading spaces in labels give the indentation level (2 spaces per level).
    """
    chart = chart if chart in CDR_SECTIONS else "asso"
    labels = _cdr_labels(chart)
    t = {key: section_total(data[key]) for key in labels}

    def lines(key):
        for line_key, label in labels[key].items():
            yield ("row", label, *data[key][line_key])

    def result(a, b):
        return (t[a][0] - t[b][0], _diff(t[a][1], t[b][1]))

    yield ("section", "PRODUITS D'EXPLOITATION", None, None)
    if chart == "asso":
        yield from _asso_produits_exploitation(data["produits_exploitation"], labels["produits_exploitation"])
    else:
        yield from lines("produits_exploitation")
    yield ("total", "TOTAL I — Produits d'exploitation", *t["produits_exploitation"])

    yield ("section", "CHARGES D'EXPLOITATION", None, None)
    yield from lines("charges_exploitation")
    yield ("total", "TOTAL II — Charges d'exploitation", *t["charges_exploitation"])
    r1 = result("produits_exploitation", "charges_exploitation")
    yield ("result", "1 — RÉSULTAT D'EXPLOITATION (I - II)", *r1)

    yield ("section", "PRODUITS FINANCIERS", None, None)
    yield from lines("produits_financiers")
    yield ("total", "TOTAL III — Produits financiers", *t["produits_financiers"])

    yield ("section", "CHARGES FINANCIÈRES", None, None)
    yield from lines("charges_financieres")
    yield ("total", "TOTAL IV — Charges financières", *t["charges_financieres"])
    r2 = result("produits_financiers", "charges_financieres")
    yield ("result", "2 — RÉSULTAT FINANCIER (III - IV)", *r2)
    yield ("result", "3 — RÉSULTAT COURANT avant impôts", r1[0] + r2[0], _add(r1[1], r2[1]))

    yield ("section", "PRODUITS EXCEPTIONNELS", None, None)
    yield from lines("produits_exceptionnels")
    yield ("total", "TOTAL V — Produits exceptionnels", *t["produits_exceptionnels"])

    yield ("section", "CHARGES EXCEPTIONNELLES", None, None)
    yield from lines("charges_exceptionnelles")
    yield ("total", "TOTAL VI — Charges exceptionnelles", *t["charges_exceptionnelles"])
    yield ("result", "4 — RÉSULTAT EXCEPTIONNEL (V - VI)",
           *result("produits_exceptionnels", "charges_exceptionnelles"))

    ps = data["participation_salaries"]
    ib = data["impots_benefices"]
    yield ("row", "Participation des salariés aux résultats (VII)", *ps)
    yield ("row", "Impôts sur les bénéfices (VIII)", *ib)

    produits = (
        t["produits_exploitation"][0] + t["produits_financiers"][0] + t["produits_exceptionnels"][0],
        _add(t["produits_exploitation"][1], t["produits_financiers"][1], t["produits_exceptionnels"][1]),
    )
    charges = (
        t["charges_exploitation"][0] + t["charges_financieres"][0]
        + t["charges_exceptionnelles"][0] + ps[0] + ib[0],
        _add(t["charges_exploitation"][1], t["charges_financieres"][1],
             t["charges_exceptionnelles"][1], ps[1], ib[1]),
    )
    yield ("total", "Total des produits (I+III+V)", *produits)
    yield ("total", "Total des charges (II+IV+VI+VII+VIII)", *charges)
    resultat = (produits[0] - charges[0], _diff(produits[1], charges[1]))
    if chart == "asso":
        yield ("result", "EXCÉDENT" if resultat[0] >= 0 else "DÉFICIT", *resultat)
    else:
        yield ("result", "BÉNÉFICE" if resultat[0] >= 0 else "PERTE", *resultat)

    if chart == "asso":
        yield ("section", "CONTRIBUTIONS VOLONTAIRES EN NATURE", None, None)
        yield from lines("contributions_produits")
        yield ("total", "Total contributions volontaires (produits)", *t["contributions_produits"])

        yield ("section", "CHARGES DES CONTRIBUTIONS VOLONTAIRES", None, None)
        yield from lines("contributions_charges")
        yield ("total", "Total contributions volontaires (charges)", *t["contributions_charges"])


def _asso_produits_exploitation(pe, labels):
    """Produits d'exploitation associatifs : sous-groupes du modèle PCA."""
    def row(key, indent=0):
        return ("row", "  " * indent + labels[key], *pe[key])

    yield row("cotisations")
    yield ("subhead", "Ventes de biens et services", None, None)
    yield row("ventes_biens", 1)
    yield row("dont_ventes_dons_nature", 2)
    yield row("ventes_prestations", 1)
    yield row("dont_parrainages", 2)
    yield ("subhead", "Produits de tiers financeurs", None, None)
    yield row("concours_publics_subventions", 1)
    yield row("versements_fondateurs_dotation", 1)
    yield ("subhead", "  Ressources liées à la générosité du public", None, None)
    yield row("dons_manuels", 2)
    yield row("mecenat", 2)
    yield row("legs_donations", 2)
    yield row("contributions_financieres", 1)
    yield row("reprises_amort_provisions")
    yield row("utilisations_fonds_dedies")
    yield row("autres_produits")
