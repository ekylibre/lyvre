"""
Build Bilan and Compte de Résultat structures matching the XLS model.
Each section aggregates account codes by prefix using database sums.
"""
from app.extensions import db
from app.models import Account, JournalLine, JournalEntry


def _sum_accounts(prefixes, fiscal_year_id, side="debit"):
    """Sum debit or credit for all accounts whose code starts with any of the given prefixes."""
    if not prefixes or not fiscal_year_id:
        return 0
    conditions = [Account.code.like(f"{p}%") for p in prefixes]
    col = JournalLine.debit_cents if side == "debit" else JournalLine.credit_cents
    result = (
        db.session.query(db.func.coalesce(db.func.sum(col), 0))
        .join(Account, Account.id == JournalLine.account_id)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .filter(JournalEntry.fiscal_year_id == fiscal_year_id)
        .filter(db.or_(*conditions))
        .scalar()
    )
    return result or 0


def _net(prefixes, fiscal_year_id):
    """Returns debit - credit (positive = debit balance)."""
    d = _sum_accounts(prefixes, fiscal_year_id, "debit")
    c = _sum_accounts(prefixes, fiscal_year_id, "credit")
    return d - c


def _net_credit(prefixes, fiscal_year_id):
    """Returns credit - debit (positive = credit balance)."""
    return -_net(prefixes, fiscal_year_id)


# ---------------------------------------------------------------------------
# BILAN
# ---------------------------------------------------------------------------

def build_bilan(fy, fy_prev=None):
    def n(prefixes):
        return _net(prefixes, fy.id) if fy else 0

    def p(prefixes):
        return _net(prefixes, fy_prev.id) if fy_prev else None

    def nc(prefixes):
        return _net_credit(prefixes, fy.id) if fy else 0

    def pc(prefixes):
        return _net_credit(prefixes, fy_prev.id) if fy_prev else None

    actif = {
        "immobilisations_incorporelles": {
            "frais_etablissement": (n(["201"]), p(["201"])),
            "frais_recherche_dev": (n(["203"]), p(["203"])),
            "donations_usufruit": (n(["204"]), p(["204"])),
            "concessions_brevets": (n(["205"]), p(["205"])),
            "immo_incorporelles_en_cours": (n(["232"]), p(["232"])),
            "avances_acomptes": (n(["237"]), p(["237"])),
        },
        "immobilisations_corporelles": {
            "terrains": (n(["211"]), p(["211"])),
            "constructions": (n(["213", "214"]), p(["213", "214"])),
            "installations_techniques": (n(["215"]), p(["215"])),
            "immo_corporelles_en_cours": (n(["231"]), p(["231"])),
            "avances_acomptes": (n(["238"]), p(["238"])),
        },
        "biens_legs_donations": (n(["24"]), p(["24"])),
        "immobilisations_financieres": {
            "participations_creances": (n(["261", "267"]), p(["261", "267"])),
            "autres_titres_immobilises": (n(["271", "272"]), p(["271", "272"])),
            "prets": (n(["274"]), p(["274"])),
            "autres": (n(["275", "276"]), p(["275", "276"])),
        },
        "stocks": (n(["31", "32", "33", "34", "35", "37"]), p(["31", "32", "33", "34", "35", "37"])),
        "creances_clients": (n(["411", "413", "416", "418"]), p(["411", "413", "416", "418"])),
        "creances_legs_donations": (n(["461"]), p(["461"])),
        "autres_creances": (n(["40", "42", "43", "44", "45", "46", "47"]), p(["40", "42", "43", "44", "45", "46", "47"])),
        "valeurs_mobilières_placement": (n(["50"]), p(["50"])),
        "instruments_tresorerie": (n(["52"]), p(["52"])),
        "disponibilites": (n(["51", "53", "54"]), p(["51", "53", "54"])),
        "charges_constatees_avance": (n(["486"]), p(["486"])),
        "frais_emission_emprunts": (n(["4816"]), p(["4816"])),
        "primes_remboursement": (n(["169"]), p(["169"])),
        "ecarts_conversion_actif": (n(["476"]), p(["476"])),
    }

    passif = {
        "fonds_propres_sans_reprise_statutaires": (nc(["1021", "1022"]), pc(["1021", "1022"])),
        "fonds_propres_sans_reprise_complementaires": (nc(["1023", "1024", "1025"]), pc(["1023", "1024", "1025"])),
        "fonds_propres_avec_reprise_statutaires": (nc(["1032"]), pc(["1032"])),
        "fonds_propres_avec_reprise_complementaires": (nc(["1034", "1035"]), pc(["1034", "1035"])),
        "ecarts_reevaluation": (nc(["105"]), pc(["105"])),
        "reserves_statutaires": (nc(["1063"]), pc(["1063"])),
        "reserves_projet": (nc(["10681"]), pc(["10681"])),
        "autres_reserves": (nc(["1062", "1064", "1068"]), pc(["1062", "1064", "1068"])),
        "report_a_nouveau": (nc(["110", "115", "119"]), pc(["110", "115", "119"])),
        "excedent_deficit": (nc(["120", "129"]), pc(["120", "129"])),
        "fonds_propres_consomptibles": (nc(["108"]), pc(["108"])),
        "subventions_investissement": (nc(["131", "138", "139"]), pc(["131", "138", "139"])),
        "provisions_reglementees": (nc(["14"]), pc(["14"])),
        "fonds_reportes_legs": (nc(["191", "192"]), pc(["191", "192"])),
        "fonds_dedies": (nc(["193", "194", "195", "196"]), pc(["193", "194", "195", "196"])),
        "provisions_risques": (nc(["151"]), pc(["151"])),
        "provisions_charges": (nc(["152", "153", "155", "157", "158"]), pc(["152", "153", "155", "157", "158"])),
        "emprunts_obligataires": (nc(["163"]), pc(["163"])),
        "emprunts_etablissements_credit": (nc(["164"]), pc(["164"])),
        "emprunts_dettes_diverses": (nc(["165", "167", "168"]), pc(["165", "167", "168"])),
        "dettes_fournisseurs": (nc(["401", "403", "404", "408"]), pc(["401", "403", "404", "408"])),
        "dettes_legs_donations": (nc(["466"]), pc(["466"])),
        "dettes_fiscales_sociales": (nc(["43", "44"]), pc(["43", "44"])),
        "dettes_immobilisations": (nc(["404", "405"]), pc(["404", "405"])),
        "autres_dettes": (nc(["419", "46", "47"]), pc(["419", "46", "47"])),
        "instruments_tresorerie_passif": (nc(["52"]), pc(["52"])),
        "produits_constates_avance": (nc(["487"]), pc(["487"])),
        "ecarts_conversion_passif": (nc(["477"]), pc(["477"])),
    }

    return {"actif": actif, "passif": passif}


# ---------------------------------------------------------------------------
# COMPTE DE RÉSULTAT
# ---------------------------------------------------------------------------

def build_compte_resultat(fy, fy_prev=None):
    def nc(prefixes):
        return _net_credit(prefixes, fy.id) if fy else 0

    def nd(prefixes):
        return _net(prefixes, fy.id) if fy else 0

    def pc(prefixes):
        return _net_credit(prefixes, fy_prev.id) if fy_prev else None

    def pd(prefixes):
        return _net(prefixes, fy_prev.id) if fy_prev else None

    produits_exploitation = {
        "cotisations": (nc(["756"]), pc(["756"])),
        "ventes_biens": (nc(["701", "702", "703", "707"]), pc(["701", "702", "703", "707"])),
        "dont_ventes_dons_nature": (nc(["7073"]), pc(["7073"])),
        "ventes_prestations": (nc(["704", "705", "706", "708"]), pc(["704", "705", "706", "708"])),
        "dont_parrainages": (nc(["7063"]), pc(["7063"])),
        "concours_publics_subventions": (nc(["74"]), pc(["74"])),
        "versements_fondateurs_dotation": (nc(["753"]), pc(["753"])),
        "dons_manuels": (nc(["75411"]), pc(["75411"])),
        "mecenat": (nc(["7542"]), pc(["7542"])),
        "legs_donations": (nc(["7543"]), pc(["7543"])),
        "contributions_financieres": (nc(["755"]), pc(["755"])),
        "reprises_amort_provisions": (nc(["781", "786", "787", "789"]), pc(["781", "786", "787", "789"])),
        "utilisations_fonds_dedies": (nc(["789"]), pc(["789"])),
        "autres_produits": (nc(["71", "72", "75", "79"]), pc(["71", "72", "75", "79"])),
    }

    charges_exploitation = {
        "achats_marchandises": (nd(["607"]), pd(["607"])),
        "variation_stocks": (nd(["603", "6037"]), pd(["603", "6037"])),
        "autres_achats_charges_externes": (nd(["60", "61", "62"]), pd(["60", "61", "62"])),
        "aides_financieres": (nd(["657"]), pd(["657"])),
        "impots_taxes": (nd(["63"]), pd(["63"])),
        "salaires_traitements": (nd(["641", "642"]), pd(["641", "642"])),
        "charges_sociales": (nd(["645", "647", "648"]), pd(["645", "647", "648"])),
        "dotations_amort_depreciations": (nd(["681", "686"]), pd(["681", "686"])),
        "dotations_provisions": (nd(["6815", "6816", "6817"]), pd(["6815", "6816", "6817"])),
        "reports_fonds_dedies": (nd(["689"]), pd(["689"])),
        "autres_charges": (nd(["65", "67", "68", "69"]), pd(["65", "67", "68", "69"])),
    }

    produits_financiers = {
        "de_participations": (nc(["761"]), pc(["761"])),
        "autres_valeurs_mobilieres": (nc(["762", "763"]), pc(["762", "763"])),
        "autres_interets": (nc(["764", "765", "766", "767", "768"]), pc(["764", "765", "766", "767", "768"])),
        "reprises_provisions": (nc(["786"]), pc(["786"])),
        "differences_positives_change": (nc(["766"]), pc(["766"])),
        "produits_nets_cessions_vmp": (nc(["767"]), pc(["767"])),
    }

    charges_financieres = {
        "dotations_amort": (nd(["686"]), pd(["686"])),
        "interets_charges": (nd(["661", "664", "665", "666", "668"]), pd(["661", "664", "665", "666", "668"])),
        "differences_negatives_change": (nd(["666"]), pd(["666"])),
        "charges_nettes_cessions_vmp": (nd(["667"]), pd(["667"])),
    }

    produits_exceptionnels = {
        "sur_operations_gestion": (nc(["771"]), pc(["771"])),
        "sur_operations_capital": (nc(["775", "777"]), pc(["775", "777"])),
        "reprises_provisions": (nc(["787"]), pc(["787"])),
    }

    charges_exceptionnelles = {
        "sur_operations_gestion": (nd(["671"]), pd(["671"])),
        "sur_operations_capital": (nd(["675", "678"]), pd(["675", "678"])),
        "dotations_amort": (nd(["687"]), pd(["687"])),
    }

    contributions_produits = {
        "dons_nature": (nc(["870"]), pc(["870"])),
        "prestations_nature": (nc(["871"]), pc(["871"])),
        "benevolat": (nc(["875"]), pc(["875"])),
    }

    contributions_charges = {
        "secours_nature": (nd(["860"]), pd(["860"])),
        "mise_dispo_biens": (nd(["861"]), pd(["861"])),
        "prestations_nature": (nd(["862"]), pd(["862"])),
        "personnel_benevole": (nd(["864"]), pd(["864"])),
    }

    participation_salaries = (nd(["691"]), pd(["691"]))
    impots_benefices = (nd(["695", "696", "699"]), pd(["695", "696", "699"]))

    return {
        "produits_exploitation": produits_exploitation,
        "charges_exploitation": charges_exploitation,
        "produits_financiers": produits_financiers,
        "charges_financieres": charges_financieres,
        "produits_exceptionnels": produits_exceptionnels,
        "charges_exceptionnelles": charges_exceptionnelles,
        "contributions_produits": contributions_produits,
        "contributions_charges": contributions_charges,
        "participation_salaries": participation_salaries,
        "impots_benefices": impots_benefices,
    }
