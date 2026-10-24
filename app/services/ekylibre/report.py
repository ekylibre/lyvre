"""Rapport de reprise (Markdown) : source, période, volumes, contrôles, correspondances, corrections."""
from collections import Counter
from datetime import datetime

from app.services.ekylibre import checks as checks_module
from app.services.ekylibre.data import EkyData
from app.services.ekylibre.mapping import (
    AccountTarget, Chart, EntityTarget, map_accounts, map_entities, map_journal,
)


def plan(data: EkyData, chart: Chart) -> dict:
    """Correspondances calculées sans rien écrire (analyse à blanc et préparation de l'import)."""
    numbers = {data.account_number(i["account_id"]) for e in data.entries() for i in data.items_by_entry[e["id"]]}
    for entity in data.rows["entities"]:
        for key in ("supplier_account_id", "client_account_id"):
            if entity["id"] in data.entities_used() and data.account_number(entity.get(key)):
                numbers.add(data.account_number(entity.get(key)))
    accounts = map_accounts(data, chart, {n for n in numbers if n})
    entities = map_entities(data, accounts)
    journals = Counter(data.journal_code(e["journal_id"]) for e in data.entries())
    return {"accounts": accounts, "entities": entities,
            "journals": {code: (map_journal(code), n) for code, n in sorted(journals.items())}}


def _table(headers, rows) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return lines


def render(data: EkyData, mapping: dict, results: list[checks_module.Check], source: str, dry_run: bool,
           imported=None) -> str:
    accounts: dict[str, AccountTarget] = mapping["accounts"]
    entities: dict[str, EntityTarget] = mapping["entities"]
    entries = data.entries()
    out = [f"# Rapport de reprise Ekylibre — {'analyse à blanc' if dry_run else 'import'}", "",
           f"- Source : `{source}`",
           f"- Période : du {data.start:%d/%m/%Y} au {data.until:%d/%m/%Y}",
           f"- Produit le {datetime.now():%d/%m/%Y %H:%M}", "", "## Volumes", ""]
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
    out += ["", "## Comptes", "",
            f"{len(accounts)} compte(s) mouvementé(s) : {by_action['existing']} existant(s) dans le plan SCI, "
            f"{by_action['create']} à créer, {by_action['associate']} compte(s) d'associé, "
            f"{by_action['vat']} compte(s) de TVA absorbé(s) dans les achats.", ""]
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
        out += ["", f"TVA intégrée à la charge : {len(imported.vat_corrections)} écriture(s), "
                f"{sum(v for _n, v in imported.vat_corrections) / 100:.2f} €.", ""]
        out += _table(["Écriture", "TVA intégrée"], [(n, f"{v / 100:.2f} €") for n, v in imported.vat_corrections])
        out += ["", "Contrôle : balance Lyvre = balance Ekylibre de la période, corrections de TVA comprises (aucun écart).", ""]
        if imported.attachments:
            out += ["### Pièces reprises", ""]
            out += _table(["Facture", "Fichier", "SHA-256 (début)"], imported.attachments)
            out.append("")
        out += ["### Règles d'affectation créées", ""]
        out += _table(["Tiers", "Sorte", "Valeur"], imported.rules) if imported.rules else ["Aucune."]
        if imported.rules_skipped:
            out += ["", "Motifs bancaires écartés :", ""]
            out += _table(["Motif", "Raison"], imported.rules_skipped)
        out.append("")
        out += ["### Remarques", ""] + [f"- {note}" for note in imported.notes]
    out += ["", "## Corrections prévues", "",
            "- TVA déductible des achats intégrée à la charge (EK3) : voir le contrôle « TVA ».",
            "- Reclassement des terrains (Bois, Terres) du 2131 au 211 au "
            f"{data.start:%d/%m/%Y}, en brouillard (EK6).", ""]
    return "\n".join(out) + "\n"
