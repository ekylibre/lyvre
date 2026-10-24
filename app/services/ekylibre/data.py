"""Données d'un export Ekylibre utiles à la reprise, indexées, avec les filtres de période.

Montants Ekylibre (`numeric`, ex. « 1234.5600 ») convertis en centimes ; dates ISO conservées en
`date`. Période : du 01/01 de l'exercice de départ à la date limite (`until`).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.services.ekylibre.reader import Source, iter_copy

TABLES = {
    "financial_years", "journals", "accounts", "entities", "entity_addresses", "journal_entries",
    "journal_entry_items", "purchases", "purchase_items", "sales", "sale_items", "outgoing_payments",
    "incoming_payments", "incoming_payment_modes", "affairs", "cashes", "bank_statements",
    "bank_statement_items", "attachments", "documents", "associates", "fixed_assets", "taxes",
}


def cents(value) -> int:
    if value in (None, ""):
        return 0
    return int((Decimal(value) * 100).quantize(Decimal(1), ROUND_HALF_UP))


def day(value) -> date | None:
    return date.fromisoformat(value[:10]) if value else None


@dataclass
class EkyData:
    start: date
    until: date
    rows: dict = field(default_factory=dict)

    # ---------------------------------------------------------------- chargement

    @classmethod
    def load(cls, source: Source, start: date, until: date) -> "EkyData":
        data = cls(start, until, {name: [] for name in TABLES})
        with source.sql_lines() as lines:
            for table, row in iter_copy(lines, TABLES):
                data.rows[table].append(row)
        data._index()
        return data

    def _index(self):
        self.by_id = {name: {r["id"]: r for r in rows if "id" in r} for name, rows in self.rows.items()}
        self.items_by_entry = defaultdict(list)
        for item in self.rows["journal_entry_items"]:
            self.items_by_entry[item["entry_id"]].append(item)
        for items in self.items_by_entry.values():
            items.sort(key=lambda i: (int(i.get("position") or 0), int(i["id"])))
        self.purchase_items = defaultdict(list)
        for item in self.rows["purchase_items"]:
            self.purchase_items[item["purchase_id"]].append(item)
        self.sale_items = defaultdict(list)
        for item in self.rows["sale_items"]:
            self.sale_items[item["sale_id"]].append(item)
        self.attachments = defaultdict(list)
        for att in self.rows["attachments"]:
            if not att.get("deleted_at"):
                self.attachments[(att["resource_type"], att["resource_id"])].append(att)
        self.statement_items_by_entry = {i["journal_entry_id"]: i for i in self.rows["bank_statement_items"]
                                         if i.get("journal_entry_id")}

    # ---------------------------------------------------------------- accès

    def get(self, table, row_id):
        return self.by_id[table].get(row_id) if row_id else None

    def account_number(self, account_id) -> str | None:
        account = self.get("accounts", account_id)
        return account["number"] if account else None

    def journal_code(self, journal_id) -> str:
        return self.get("journals", journal_id)["code"]

    def in_period(self, value) -> bool:
        when = day(value) if not isinstance(value, date) else value
        return when is not None and self.start <= when <= self.until

    # ---------------------------------------------------------------- période

    def entries(self) -> list[dict]:
        """Écritures de la période (dont les à-nouveaux de l'exercice de départ), par date puis numéro."""
        rows = [e for e in self.rows["journal_entries"] if self.in_period(e["printed_on"])]
        return sorted(rows, key=lambda e: (e["printed_on"], e["number"] or "", int(e["id"])))

    def entries_after(self) -> list[dict]:
        return sorted((e for e in self.rows["journal_entries"] if day(e["printed_on"]) > self.until),
                      key=lambda e: e["printed_on"])

    def purchases(self) -> list[dict]:
        return [p for p in self.rows["purchases"] if self.in_period(p.get("invoiced_at"))]

    def sales(self) -> list[dict]:
        return [s for s in self.rows["sales"] if self.in_period(s.get("invoiced_at") or s.get("created_at"))]

    def outgoing_payments(self) -> list[dict]:
        return [o for o in self.rows["outgoing_payments"] if self.in_period(o.get("paid_at") or o.get("to_bank_at"))]

    def incoming_payments(self) -> list[dict]:
        return [o for o in self.rows["incoming_payments"] if self.in_period(o.get("paid_at") or o.get("to_bank_at"))]

    def statement_items(self) -> list[dict]:
        return sorted((i for i in self.rows["bank_statement_items"] if self.in_period(i.get("transfered_on"))),
                      key=lambda i: (i["transfered_on"], int(i["id"])))

    def fiscal_year(self, on: date) -> dict | None:
        return next((fy for fy in self.rows["financial_years"]
                     if day(fy["started_on"]) <= on <= day(fy["stopped_on"])), None)

    def documents_of(self, resource_type, resource_id) -> list[dict]:
        return [self.get("documents", a["document_id"]) for a in self.attachments.get((resource_type, resource_id), [])
                if self.get("documents", a["document_id"])]

    def entities_used(self) -> set[str]:
        """Tiers utiles : fournisseurs, clients, payeurs de la période, associés, tiers des comptes mouvementés."""
        ids = {p["supplier_id"] for p in self.purchases()} | {s["client_id"] for s in self.sales()}
        ids |= {o["payee_id"] for o in self.outgoing_payments()} | {o["payer_id"] for o in self.incoming_payments()}
        ids |= {a["entity_id"] for a in self.rows["associates"]}
        used_accounts = {i["account_id"] for e in self.entries() for i in self.items_by_entry[e["id"]]}
        for entity in self.rows["entities"]:
            if {entity.get("supplier_account_id"), entity.get("client_account_id")} & used_accounts:
                ids.add(entity["id"])
        return {i for i in ids if i}
