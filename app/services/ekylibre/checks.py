"""Contrôles préalables d'un export Ekylibre (rapport de reprise, anomalies A1–A9 des besoins)."""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from app.services.ekylibre.data import EkyData, cents, day


@dataclass
class Check:
    key: str
    label: str
    ok: bool
    details: list = field(default_factory=list)
    blocking: bool = False   # bloquant : l'import est refusé ; sinon anomalie signalée au rapport


def _signed(item) -> int:
    return cents(item["real_debit"]) - cents(item["real_credit"])


def balances(data: EkyData, entries, exclude_journals=()) -> Counter:
    result = Counter()
    for entry in entries:
        if data.journal_code(entry["journal_id"]) in exclude_journals:
            continue
        for item in data.items_by_entry[entry["id"]]:
            result[data.account_number(item["account_id"])] += _signed(item)
    return result


def opening_entries(data: EkyData) -> list[dict]:
    return [e for e in data.entries() if data.journal_code(e["journal_id"]) == "RG" and day(e["printed_on"]) == data.start]


def vat_lines(data: EkyData) -> list[tuple[dict, dict]]:
    """Lignes de TVA déductible (4456x) des écritures d'achat de la période (ACHA, BANQ d'achats `at_paying`)."""
    at_paying = {p["journal_entry_id"] for p in data.purchases() if p.get("tax_payability") == "at_paying"}
    found = []
    for entry in data.entries():
        journal = data.journal_code(entry["journal_id"])
        if journal == "RG" or (journal != "ACHA" and entry["id"] not in at_paying and entry.get("resource_type") != "Purchase"):
            continue
        for item in data.items_by_entry[entry["id"]]:
            if (data.account_number(item["account_id"]) or "").startswith("4456"):
                found.append((entry, item))
    return found


def run(data: EkyData, profile=None, entities=None) -> list[Check]:
    """Contrôles de la sauvegarde. `profile` : profil de restauration (défaut : reprise SCI) ;
    `entities` : tiers après correspondance (noms rendus uniques, Q5)."""
    from app.services.ekylibre import profile as profiles
    profile = profile or profiles.sci(data.start, data.until)
    checks = []
    entries = data.entries()

    unbalanced = [f"{e['number']} ({e['printed_on']}) : {sum(_signed(i) for i in data.items_by_entry[e['id']]) / 100:.2f} €"
                  for e in entries if sum(_signed(i) for i in data.items_by_entry[e["id"]])]
    checks.append(Check("balanced", f"Écritures de la période équilibrées ({len(entries)})", not unbalanced, unbalanced,
                        blocking=True))

    previous = data.fiscal_year(data.start - timedelta(days=1))
    if previous is not None and (profile.is_sci or opening_entries(data)):
        prior = [e for e in data.rows["journal_entries"] if e["financial_year_id"] == previous["id"]]
        end = balances(data, prior, exclude_journals=("CL",))
        opening = balances(data, opening_entries(data))
        diffs = []
        for number in sorted(set(end) | set(opening)):
            if number and number[:1] in "12345" and end[number] != opening[number]:
                diffs.append(f"{number} : fin {previous['code']} {end[number] / 100:.2f} €, à-nouveaux {opening[number] / 100:.2f} €")
        # Affectation du résultat (12x → 11x) : écart attendu ; on la neutralise pour ne garder que l'inattendu.
        result_moves = sum(end[n] - opening[n] for n in set(end) | set(opening) if n and n[:2] in ("11", "12"))
        unexpected = [d for d in diffs if not d.startswith(("11", "12"))] if result_moves == 0 else diffs
        checks.append(Check("opening", f"À-nouveaux du {data.start:%d/%m/%Y} = soldes de fin {previous['code']} "
                            "(affectation du résultat mise à part)", not unexpected, unexpected))

    bank = [c for c in data.rows["cashes"] if c.get("nature") == "bank_account"]
    for cash in bank:
        statements = {s["id"] for s in data.rows["bank_statements"] if s["cash_id"] == cash["id"]}
        statement_balance = sum(cents(i["credit"]) - cents(i["debit"]) for i in data.rows["bank_statement_items"]
                                if i["bank_statement_id"] in statements and day(i["transfered_on"]) <= data.until)
        account = data.account_number(cash["main_account_id"])
        # Profil standard : les à-nouveaux sont calculés (lot RE2), le solde se compare donc en cumul depuis l'origine.
        scope = entries if profile.is_sci else [e for e in data.rows["journal_entries"] if day(e["printed_on"]) <= data.until]
        ledger = balances(data, scope)[account]
        checks.append(Check(f"bank_{cash['id']}", f"Solde {account} au {data.until:%d/%m/%Y} = relevés ({cash['name']})",
                            ledger == statement_balance,
                            [f"Comptabilité {ledger / 100:.2f} €, relevés {statement_balance / 100:.2f} €"]))
        linked = set(data.statement_items_by_entry)
        loose = [f"{e['number']} {e['printed_on']} {e['name']}" for e in entries
                 if data.journal_code(e["journal_id"]) == "BANQ" and e["id"] not in linked]
        checks.append(Check("bank_unlinked", f"Écritures BANQ sans ligne de relevé ({len(loose)}) : reprises, non rapprochées",
                            True, loose))

    after = data.entries_after()
    checks.append(Check("after", f"Écritures après le {data.until:%d/%m/%Y} non reprises ({len(after)})", True,
                        [f"{e['number']} {e['printed_on']} {e['name']}" for e in after]))

    vat = vat_lines(data)
    if profile.absorb_purchase_vat:
        opening_vat = sum(v for n, v in balances(data, opening_entries(data)).items() if n and n.startswith("4456"))
        checks.append(Check("vat", f"TVA déductible des achats de la période intégrée à la charge (EK3) : "
                            f"{sum(_signed(i) for _e, i in vat) / 100:.2f} € sur {len({e['id'] for e, _i in vat})} écriture(s)",
                            True, [f"Solde d'ouverture 4456x non traité (P1) : {opening_vat / 100:.2f} €"]))
    else:
        checks.append(Check("vat", f"TVA déductible conservée en 4456x (structure assujettie) : "
                            f"{sum(_signed(i) for _e, i in vat) / 100:.2f} € sur {len({e['id'] for e, _i in vat})} écriture(s) d'achat",
                            True))

    missing = Counter(p["invoiced_at"][:4] for p in data.purchases() if not data.documents_of("Purchase", p["id"]))
    checks.append(Check("purchase_documents", "Factures d'achat sans pièce", True,
                        [f"{year} : {n}" for year, n in sorted(missing.items())]))

    if profile.validate_rule == "confirmed":
        states = Counter((e["printed_on"][:4], e["state"]) for e in entries)
        checks.append(Check("states", "États des écritures (EK2 : confirmées validées, autres en brouillard)", True,
                            [f"{y} {s} : {n}" for (y, s), n in sorted(states.items())]))
    else:
        years = {fy["id"]: fy for fy in data.rows["financial_years"]}
        states = Counter((e["printed_on"][:4], "validée" if profile.should_validate(e, years.get(e["financial_year_id"]))
                          else "brouillard") for e in entries)
        checks.append(Check("states", "États des écritures (Q4 : validées si confirmées ou si l'exercice est verrouillé "
                            "dans Ekylibre, brouillard sinon)", True,
                            [f"{y} {s} : {n}" for (y, s), n in sorted(states.items())]))

    partial = [i for e in entries for i in data.items_by_entry[e["id"]] if (i.get("letter") or "").endswith("*")]
    entry_ids = {e["id"] for e in entries}
    letters = defaultdict(set)
    for item in data.rows["journal_entry_items"]:
        if item.get("letter"):
            letters[(item["account_id"], item["letter"].rstrip("*"))].add(item["entry_id"] in entry_ids)
    spanning = [f"{data.account_number(a)} lettre {l}" for (a, l), inside in letters.items() if inside == {True, False}]
    checks.append(Check("letters", f"Lettrages : {len(partial)} ligne(s) partielle(s) ; {len(spanning)} lettrage(s) "
                        "à cheval sur la période (repris partiellement)", True, spanning[:30]))

    if profile.is_sci or data.rows["associates"]:
        checks.append(_registry_check(data))

    assets = data.rows["fixed_assets"]
    by_account = Counter(data.account_number(a.get("asset_account_id")) for a in assets)
    checks.append(Check("assets", f"Immobilisations : {len(assets)} fiche(s), {sum(cents(a['depreciable_amount']) for a in assets) / 100:.2f} €",
                        True, [f"{a['name']} : {cents(a['depreciable_amount']) / 100:.2f} € ({data.account_number(a.get('asset_account_id'))}, "
                               f"méthode {a['depreciation_method']})" for a in assets] + [f"Comptes : {dict(by_account)}"]))

    if entities is not None:
        names = Counter(e.name.strip().lower() for e in entities.values())
        renamed = [f"{e.original_name} → {e.name}" for e in sorted(entities.values(), key=lambda e: e.name.lower())
                   if e.original_name]
        if renamed:
            checks.append(Check("entity_renamed", f"Tiers de même nom rendus uniques (Q5) : {len(renamed)}", True, renamed))
    else:
        names = Counter((data.get("entities", i)["full_name"] or "").strip().lower() for i in data.entities_used())
    duplicates = [n for n, c in names.items() if c > 1]
    checks.append(Check("entity_names", "Noms de tiers uniques (fiches Lyvre)", not duplicates, duplicates, blocking=True))

    opening = balances(data, opening_entries(data))
    watch = [f"{n} : {v / 100:.2f} €" for n, v in sorted(opening.items()) if n and n.startswith("4552") and v]
    if watch:
        checks.append(Check("manager_account", "Compte courant du gérant à l'ouverture (P5)", True, watch))
    return checks


def _registry_check(data: EkyData) -> Check:
    shares = sum(int(a["share_quantity"] or 0) for a in data.rows["associates"] if a.get("associate_nature") in ("owner", "usufructuary"))
    unit = cents(next((a.get("share_unit_amount") for a in data.rows["associates"] if a.get("share_unit_amount")), "10"))
    capital = -sum(v for n, v in balances(data, opening_entries(data)).items() if n and n.startswith("101"))
    return Check("associates", f"Registre : {shares} parts × {unit / 100:.2f} € = {shares * unit / 100:.2f} € ; "
                 f"capital (101…) : {capital / 100:.2f} €", shares * unit == capital)
