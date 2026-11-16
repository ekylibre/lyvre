"""Rapport de reprise (Markdown) : source, période, volumes, contrôles, correspondances, corrections."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal

from app.services.ekylibre import checks as checks_module
from app.services.ekylibre.data import EkyData, cents, day
from app.services.ekylibre.mapping import (
    AccountTarget, Chart, EntityTarget, map_accounts, map_entities, map_journal,
)


def plan(data: EkyData, chart: Chart, profile=None) -> dict:
    """Correspondances calculées sans rien écrire (analyse à blanc et préparation de l'import)."""
    from app.services.ekylibre import opening as opening_module
    opening = None
    if opening_module.needed(data, profile):     # lot RE2 : comptes portés par les à-nouveaux calculés
        opening = opening_module.compute(data)
        data.opening_account_ids = opening_module.account_ids(data, opening)
    numbers = {data.account_number(i["account_id"]) for e in data.entries() for i in data.items_by_entry[e["id"]]}
    if opening is not None:
        numbers |= set(opening.balances)
    for entity in data.rows["entities"]:
        for key in ("supplier_account_id", "client_account_id"):
            if entity["id"] in data.entities_used() and data.account_number(entity.get(key)):
                numbers.add(data.account_number(entity.get(key)))
    absorb = profile.absorb_purchase_vat if profile is not None else True
    accounts = map_accounts(data, chart, {n for n in numbers if n}, absorb_vat=absorb,
                            reclass_stock=profile is not None and profile.stock_reclass)
    entities = map_entities(data, accounts, dedupe=profile is not None and profile.dedupe_entity_names)
    journals = Counter(data.journal_code(e["journal_id"]) for e in data.entries())
    return {"accounts": accounts, "entities": entities, "opening": opening,
            "journals": {code: (map_journal(code), n) for code, n in sorted(journals.items())}}


def _euros(amount: int) -> str:
    return f"{amount / 100:,.2f} €".replace(",", " ").replace(".", ",")


def _code(accounts: dict, number: str | None) -> str:
    target = accounts.get(number) if number else None
    return f"{number} → {target.code}" if target is not None else (number or "—")


PERIODS = {"month": "mois", "trimester": "trimestres", "semester": "semestres", "year": "ans"}


def loans_section(data: EkyData, accounts: dict) -> list[str]:
    """Emprunts (lot RE3) : Lyvre n'a pas de fiche d'emprunt ; écritures reprises, échéancier résumé ici."""
    loans = data.loans()
    if not loans:
        return []
    out = ["", "## Emprunts", "",
           "Lyvre n'a pas de fiche d'emprunt : les écritures d'Ekylibre (déblocage, échéances passées) sont reprises ; "
           "les échéances à venir ne sont pas créées. Capital restant dû (échéancier) comparé au solde du compte "
           "d'emprunt : un écart vient d'échéances échues non passées en écriture dans Ekylibre.", ""]
    rows = []
    balances = data.balances_before(data.until + timedelta(days=1))
    for loan in loans:
        repayments = data.repayments_of(loan["id"])
        due = [r for r in repayments if day(r["due_on"]) <= data.until]
        remaining = cents(due[-1]["remaining_amount"]) if due else cents(loan["amount"])
        number = data.account_number(loan.get("loan_account_id"))
        balance = -balances.get(number, 0) if number else 0
        lender = (data.get("entities", loan.get("lender_id")) or {}).get("full_name") or "—"
        booked = sum(1 for r in due if r.get("journal_entry_id"))
        rows.append((loan.get("name") or "—", lender, _euros(cents(loan["amount"])), f"{day(loan['started_on']):%d/%m/%Y}",
                     f"{loan.get('repayment_duration')} {PERIODS.get(loan.get('repayment_period'), loan.get('repayment_period'))}",
                     f"{float(loan.get('interest_percentage') or 0):.2f} %".replace(".", ","),
                     f"{len(due)} / {len(repayments)}", f"{booked} / {len(due)}", _euros(remaining), _code(accounts, number),
                     _euros(balance) + ("" if balance == remaining else " ⚠️")))
    out += _table(["Emprunt", "Prêteur", "Montant", "Début", "Durée", "Taux", "Échéances échues", "Passées en écriture",
                   "Capital restant dû",
                   "Compte", "Solde du compte"], rows)
    return out + [""]


def foreign_vat_section(data: EkyData, accounts: dict, profile=None) -> list[str]:
    """D-R3 : ventes à taux étrangers (ventes à distance dans l'Union), à vérifier sur le guichet unique (OSS)."""
    states = profile.sales_states if profile is not None else None
    totals = defaultdict(lambda: [0, 0, 0, set()])
    for sale in data.sales():
        if states is not None and sale.get("state") not in states:
            continue
        for item in data.sale_items[sale["id"]]:
            tax = data.get("taxes", item.get("tax_id")) or {}
            if (tax.get("country") or "fr") == "fr":
                continue
            row = totals[(tax["country"].upper(), tax.get("amount"))]
            pretax = cents(item.get("pretax_amount"))
            row[0] += 1
            row[1] += pretax
            row[2] += cents(item.get("amount")) - pretax
            row[3].add(_code(accounts, data.account_number(tax.get("collect_account_id"))))
    if not totals:
        return []
    out = ["", "## TVA étrangère des ventes (OSS)", "",
           "Taux repris tels quels sur les lignes de vente, TVA sur le compte de collecte d'Ekylibre (D-R3). "
           "Lyvre ne déclare pas le guichet unique : vérifier ces montants sur la déclaration OSS, et que ces comptes "
           "sont bien exclus de la CA3.", ""]
    out += _table(["Pays", "Taux", "Lignes", "Base HT", "TVA", "Compte"],
                  [(country, f"{float(rate or 0):g} %".replace(".", ","), n, _euros(base), _euros(vat), ", ".join(sorted(acc)))
                   for (country, rate), (n, base, vat, acc) in sorted(totals.items())])
    return out + [""]


def agronomy_section(data: EkyData, accounts: dict, profile=None) -> list[str]:
    """Lot RE4 : reclassement des stocks, activités et surfaces, dernier inventaire et son contrôle (D-R2 révisé)."""
    from app.services.ekylibre import agronomy
    out = []
    reclassed = sorted((t for t in accounts.values() if t.action == "reclass"), key=lambda t: t.code)
    if reclassed:
        out += ["", "## Reclassement des comptes de stock", "",
                "Ancien plan agricole d'Ekylibre (30 approvisionnements, 37 produits) ramené au plan agricole de Lyvre "
                "(31 / 32 approvisionnements, 33 en-cours, 35 produits, 37 marchandises). Soldes inchangés et contrôlés.", ""]
        out += _table(["Ekylibre", "Libellé", "Lyvre", "Libellé Lyvre"], [(t.eky_number, t.eky_label, t.code, t.label) for t in reclassed])
    if profile is None or profile.is_sci or profile.chart != "agri" or not profile.agronomy:
        return out + ([""] if out else [])
    years = agronomy.campaign_years(data)
    areas = agronomy.surfaces(data)
    out += ["", "## Activités et surfaces", "", f"Campagnes : {', '.join(str(y) for y in years) or 'aucune'}.", ""]
    rows = []
    for activity in sorted(data.rows["activities"], key=lambda a: (a.get("name") or "").lower()):
        cells = [str(areas[(activity["id"], y)].quantize(Decimal("0.01"))).replace(".", ",") if (activity["id"], y) in areas else ""
                 for y in years]
        rows.append((activity.get("name") or "—", activity.get("family") or "—", activity.get("nature") or "—",
                     activity.get("production_cycle") or "—", *cells))
    out += _table(["Activité", "Famille", "Nature", "Cycle", *[f"{y} (ha)" for y in years]], rows)
    if "stock" not in profile.agronomy:
        return out + [""]
    inventory = agronomy.last_inventory(data)
    out += ["", "## Dernier inventaire", ""]
    if inventory is None:
        return out + ["Aucun inventaire passé en comptabilité dans la période.", ""]
    end = day(inventory.fiscal_year["stopped_on"])
    out += [f"Inventaires de l'exercice clos le {end:%d/%m/%Y} : {', '.join(inventory.names)} — {len(inventory.lines)} "
            f"ligne(s), {_euros(inventory.total)}. Repris en lignes d'inventaire de l'exercice, **sans écriture** : la "
            "variation est dans les écritures d'inventaire d'Ekylibre.", "",
            "Contrôle : valeur de l'inventaire et solde des comptes de stock à la clôture. Un écart signifie que "
            "l'écriture de stock calculée par Lyvre pour cet exercice ne sera pas neutre (elle ramènera les comptes "
            "à l'inventaire) : à examiner avec l'expert-comptable avant de la passer.", ""]
    grouped = defaultdict(lambda: [set(), 0, 0])                 # compte Lyvre → (comptes Ekylibre, inventaire, solde)
    for number, value, balance in agronomy.stock_control(data, inventory):
        target = accounts.get(number)
        row = grouped[target.code if target else number]
        row[0].add(number)
        row[1] += value
        row[2] += balance
    rows = [(f"{code} ({', '.join(sorted(numbers))})", _euros(value), _euros(balance),
             _euros(balance - value) + (" ⚠️" if balance != value else "")) for code, (numbers, value, balance) in sorted(grouped.items())]
    value, balance = sum(r[1] for r in grouped.values()), sum(r[2] for r in grouped.values())
    rows.append(("**Total**", f"**{_euros(value)}**", f"**{_euros(balance)}**", f"**{_euros(balance - value)}**"))
    out += _table(["Compte Lyvre (Ekylibre)", "Inventaire", "Solde du compte", "Écart"], rows)
    return out + [""]


def _table(headers, rows) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return lines


def render(data: EkyData, mapping: dict, results: list[checks_module.Check], source: str, dry_run: bool,
           imported=None, profile=None) -> str:
    accounts: dict[str, AccountTarget] = mapping["accounts"]
    entities: dict[str, EntityTarget] = mapping["entities"]
    entries = data.entries()
    out = [f"# Rapport de reprise Ekylibre — {'analyse à blanc' if dry_run else 'import'}", "",
           f"- Source : `{source}`",
           f"- Période : du {data.start:%d/%m/%Y} au {data.until:%d/%m/%Y}",
           f"- Produit le {datetime.now():%d/%m/%Y %H:%M}"]
    if profile is not None and not profile.is_sci:
        out += [f"- {line}" for line in profile.describe()]
    out += ["", "## Volumes", ""]
    out += _table(["Élément", "Nombre"], [
        ("Écritures (dont à-nouveaux)", len(entries)),
        ("Lignes d'écriture", sum(len(data.items_by_entry[e["id"]]) for e in entries)),
        ("Factures d'achat", len(data.purchases())),
        ("Pièces de vente", len(data.sales())),
        ("Règlements fournisseurs", len(data.outgoing_payments())),
        ("Encaissements", len(data.incoming_payments())),
        ("Lignes de relevé bancaire", len(data.statement_items())),
        ("Associés (lignes de registre)", len(data.rows["associates"])),
        ("Immobilisations", len(data.rows["fixed_assets"])),
        ("Tiers repris", len(entities)),
    ])
    failed = [c for c in results if not c.ok and c.blocking]
    warnings = [c for c in results if not c.ok and not c.blocking]
    out += ["", "## Contrôles", "", (f"**{len(failed)} contrôle(s) bloquant(s) en échec**" if failed
            else "Contrôles bloquants passés") + f", {len(warnings)} anomalie(s) signalée(s) (⚠️), {len(results)} contrôles.", ""]
    for check in results:
        out.append(f"- {'✅' if check.ok else ('❌' if check.blocking else '⚠️')} {check.label}")
        out += [f"  - {d}" for d in check.details[:40]]
        if len(check.details) > 40:
            out.append(f"  - … ({len(check.details) - 40} de plus)")
    out += ["", "## Journaux", ""]
    out += _table(["Ekylibre", "Lyvre", "Écritures"], [(k, v[0], v[1]) for k, v in mapping["journals"].items()])
    by_action = Counter(t.action for t in accounts.values())
    chart_name = profile.chart if profile is not None else "sci"
    out += ["", "## Comptes", "",
            f"{len(accounts)} compte(s) mouvementé(s) : {by_action['existing']} existant(s) dans le plan {chart_name.upper() if chart_name == 'sci' else chart_name}, "
            f"{by_action['create']} à créer, {by_action['associate']} compte(s) d'associé"
            + (f", {by_action['reclass']} compte(s) de stock reclassé(s)" if by_action["reclass"] else "")
            + (f", {by_action['vat']} compte(s) de TVA absorbé(s) dans les achats." if by_action["vat"] else "."), ""]
    out += _table(["Ekylibre", "Libellé", "Lyvre", "Action", "Rattaché à"],
                  [(t.eky_number, t.eky_label, t.code, t.action, t.parent or "") for t in
                   sorted(accounts.values(), key=lambda t: t.code)])
    out += ["", "## Tiers", ""]
    out += _table(["Nom", "Type", "Fournisseur", "Client", "SIRET", "TVA", "IBAN", "Ville"],
                  [(e.name, e.entity_type, e.supplier_code or "", e.customer_code or "", e.siret or "", e.vat_number or "",
                    "oui" if e.iban else "", e.city or "") for e in sorted(entities.values(), key=lambda e: e.name.lower())])
    if imported is not None:
        out += ["", "## Import", ""]
        out += _table(["Élément", "Nombre"], sorted(imported.stats.items()))
        if imported.vat_corrections:
            out += ["", f"TVA intégrée à la charge : {len(imported.vat_corrections)} écriture(s), "
                    f"{sum(v for _n, v in imported.vat_corrections) / 100:.2f} €.", ""]
            out += _table(["Écriture", "TVA intégrée"], [(n, f"{v / 100:.2f} €") for n, v in imported.vat_corrections])
        if getattr(imported, "opening", None) is not None:
            out += ["", "Contrôle (RE-C6) : à la fin de chaque exercice repris, solde de chaque compte dans Lyvre = solde "
                    "cumulé d'Ekylibre depuis l'origine, résultats antérieurs portés sur les comptes de D-R1 (aucun écart).", ""]
        else:
            out += ["", "Contrôle : balance Lyvre = balance Ekylibre de la période, corrections de TVA comprises (aucun écart).", ""]
        if imported.attachments:
            out += ["### Pièces reprises", ""]
            out += _table(["Pièce", "Fichier", "SHA-256 (début)"], imported.attachments)
            out.append("")
        out += ["### Règles d'affectation créées", ""]
        out += _table(["Tiers", "Sorte", "Valeur"], imported.rules) if imported.rules else ["Aucune."]
        if imported.rules_skipped:
            out += ["", "Motifs bancaires écartés :", ""]
            out += _table(["Motif", "Raison"], imported.rules_skipped)
        out.append("")
        out += ["### Remarques", ""] + [f"- {note}" for note in imported.notes]
    if profile is not None and not profile.is_sci:
        out += (loans_section(data, accounts) + foreign_vat_section(data, accounts, profile)
                + agronomy_section(data, accounts, profile))
    corrections = []
    if profile is None or profile.absorb_purchase_vat:
        corrections.append("- TVA déductible des achats intégrée à la charge (EK3) : voir le contrôle « TVA ».")
    if profile is None or profile.land_reclass:
        corrections.append("- Reclassement des terrains (Bois, Terres) du 2131 au 211 au "
                           f"{data.start:%d/%m/%Y}, en brouillard (EK6).")
    out += ["", "## Corrections prévues", ""] + (corrections or ["Aucune."]) + [""]
    return "\n".join(out) + "\n"
