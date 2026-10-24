"""Écriture de la reprise dans la base de l'instance courante (lot K2 : E1 structure, E2 associés,
E3 écritures avec TVA corrigée et états, E7 lettrage, contrôle des balances).

Les écritures d'Ekylibre sont la référence (K-C5) : reprises une à une par `ledger.post_entry`
(source `EKYLIBRE`, à-nouveaux en source `OPENING`), seules corrections : TVA déductible des achats
intégrée à la charge (EK3). Les écritures confirmées dans Ekylibre sont validées (lot `import`),
les autres restent en brouillard (EK2).
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from app.extensions import db
from app.models import (
    Account, Associate, BankAccount, Product, Rule, BankTransaction, Entity, FiscalYear, Journal, JournalEntry, Lettering, Purchase,
    PurchaseLine, PurchasePayment, Sale, SaleLine, SalePayment, ShareMovement, ShareMovementLine,
)
from app.models.journal_entry import SOURCE_OPENING
from app.services import lettering, validation
from app.services.ekylibre.checks import vat_lines
from app.services.ekylibre.data import EkyData, cents, day
from app.services.ekylibre.mapping import JOURNAL_LABELS, AccountTarget, Chart, EntityTarget, map_journal
from app.services.ledger import post_entry

SOURCE_EKYLIBRE = "EKYLIBRE"
NATURES = {"owner": "full", "usufructuary": "usufruct", "bare_owner": "bare"}
ACCOUNT_TYPES = {"1": "EQUITY", "2": "ASSET", "3": "ASSET", "4": "TIERS", "5": "ASSET", "6": "EXPENSE", "7": "REVENUE"}


class ImportFailure(Exception):
    pass


@dataclass
class Context:
    data: EkyData
    chart: Chart
    accounts_plan: dict[str, AccountTarget]
    entities_plan: dict[str, EntityTarget]
    accounts: dict[str, Account] = field(default_factory=dict)        # numéro Ekylibre → compte Lyvre
    entities: dict[str, Entity] = field(default_factory=dict)         # id Ekylibre → tiers
    journals: dict[str, Journal] = field(default_factory=dict)        # code Lyvre → journal
    years: dict[str, FiscalYear] = field(default_factory=dict)        # id d'exercice Ekylibre → exercice
    entries: dict[str, JournalEntry] = field(default_factory=dict)    # id d'écriture Ekylibre
    lines: dict[str, object] = field(default_factory=dict)            # id de ligne Ekylibre → ligne
    vat_corrections: list = field(default_factory=list)               # (numéro, TVA absorbée)
    deltas: Counter = field(default_factory=Counter)                  # id de ligne → correction (centimes)
    absorbed: set = field(default_factory=set)                        # lignes de TVA d'achat retirées
    stats: Counter = field(default_factory=Counter)
    notes: list = field(default_factory=list)
    bank_accounts: dict = field(default_factory=dict)                 # id de caisse Ekylibre → compte bancaire
    transactions: dict = field(default_factory=dict)                  # id de ligne de relevé → transaction
    purchases: dict = field(default_factory=dict)                     # id d'achat Ekylibre → facture d'achat
    sales: dict = field(default_factory=dict)                         # id de vente Ekylibre → pièce de vente
    attachments: list = field(default_factory=list)                   # (n° de facture, fichier, empreinte)
    rules: list = field(default_factory=list)                         # (tiers, sorte, valeur)
    rules_skipped: list = field(default_factory=list)                 # (motif, raison)


# ------------------------------------------------------------------ E1 structure


def _account(ctx: Context, target: AccountTarget) -> Account:
    account = Account.query.filter_by(code=target.code).first()
    if account is None:
        parent = Account.query.filter_by(code=target.parent).first() if target.parent else None
        account = Account(code=target.code, label=target.label[:255],
                          account_type=ACCOUNT_TYPES.get(target.code[:1], "OTHER"), parent=parent)
        db.session.add(account)
        db.session.flush()
        ctx.stats["accounts_created"] += 1
    elif account.is_header:
        raise ImportFailure(f"Compte {target.code} : compte de regroupement dans Lyvre (Ekylibre {target.eky_number}).")
    return account


def step_structure(ctx: Context) -> None:
    data = ctx.data
    for fy in data.rows["financial_years"]:
        start, end = day(fy["started_on"]), day(fy["stopped_on"])
        if end < data.start or start > data.until:
            continue
        label = fy["code"].replace("EX", "") if fy.get("code") else str(end.year)
        existing = FiscalYear.query.filter_by(start_date=start, end_date=end).first()
        ctx.years[fy["id"]] = existing or FiscalYear(label=label, start_date=start, end_date=end, vat_liable=False)
        db.session.add(ctx.years[fy["id"]])
    for entry in data.entries():
        code = map_journal(data.journal_code(entry["journal_id"]))
        if code not in ctx.journals:
            journal = Journal.query.filter_by(code=code).first()
            if journal is None:
                journal = Journal(code=code, label=JOURNAL_LABELS.get(code, code))
                db.session.add(journal)
            ctx.journals[code] = journal
    db.session.flush()
    for number, target in ctx.accounts_plan.items():
        if target.action in ("existing", "create", "vat"):  # 4456x : soldes d'ouverture (lignes d'achat absorbées)
            ctx.accounts[number] = _account(ctx, target)
    for eky_id, target in ctx.entities_plan.items():
        entity = Entity.query.filter_by(name=target.name).first() or Entity(name=target.name)
        entity.entity_type, entity.person_kind = target.entity_type, target.person_kind
        entity.siret, entity.vat_number, entity.iban = target.siret, target.vat_number, target.iban
        entity.address_line1, entity.postal_code, entity.city = target.address_line1, target.postal_code, target.city
        entity.account_code, entity.customer_account_code = target.supplier_code, target.customer_code
        db.session.add(entity)
        ctx.entities[eky_id] = entity
    db.session.flush()
    ctx.stats["entities"] = len(ctx.entities)


# ------------------------------------------------------------------ E2 associés


def step_associates(ctx: Context) -> None:
    data = ctx.data
    rows = data.rows["associates"]
    if not rows:
        return
    by_entity = {}
    for row in rows:
        entity = ctx.entities.get(row["entity_id"])
        if entity is None:
            raise ImportFailure(f"Associé sans tiers repris (entité Ekylibre {row['entity_id']}).")
        if entity.id in by_entity:
            continue
        number = data.account_number(row.get("associate_account_id"))
        target = ctx.accounts_plan.get(number or "")
        if target is not None:
            code = target.code
        else:
            from app.services.associates import next_account_code
            code = next_account_code()
        account = Account.query.filter_by(code=code).first()
        if account is None:
            account = Account(code=code, label=f"Compte courant — {entity.name}"[:255], account_type="TIERS",
                              parent=Account.query.filter_by(code="455").first())
            db.session.add(account)
            db.session.flush()
        if number:
            ctx.accounts[number] = account
        by_entity[entity.id] = Associate(entity=entity, account=account)
        db.session.add(by_entity[entity.id])
    db.session.flush()
    # Une reprise au dernier jour d'entrée dans le registre (nue-propriété = usufruit dans un même mouvement).
    starts = [day(r["started_on"]) for r in rows if r.get("started_on")]
    when = max(starts) if starts else ctx.data.start
    nominal = cents(next((r["share_unit_amount"] for r in rows if r.get("share_unit_amount")), "0")) or None
    lines = []
    for row in rows:
        nature = NATURES.get(row.get("associate_nature"))
        if nature is None or row.get("stopped_on"):
            continue
        associate = by_entity[ctx.entities[row["entity_id"]].id]
        lines.append(ShareMovementLine(associate_id=associate.id, nature=nature, parts=int(row["share_quantity"] or 0)))
    dates = ", ".join(sorted({f"{d:%d/%m/%Y}" for d in starts}))
    movement = ShareMovement(movement_date=when, kind="opening", nominal_cents=nominal, lines=lines,
                             description=f"Reprise Ekylibre (entrées au registre : {dates})")
    from app.services import share_register
    share_register._check_kind("opening", [(l.associate_id, l.nature, l.parts) for l in lines])  # noqa: SLF001
    db.session.add(movement)
    db.session.flush()
    ctx.stats["associates"] = len(by_entity)
    ctx.stats["share_parts"] = sum(l.parts for l in lines if l.nature in ("full", "usufruct"))


# ------------------------------------------------------------------ E3 écritures


def _vat_plan(ctx: Context) -> dict[str, int]:
    """Ligne Ekylibre → correction (centimes) : TVA retirée de sa ligne, ajoutée aux lignes de charge."""
    deltas, by_entry = Counter(), defaultdict(list)
    for entry, item in vat_lines(ctx.data):
        by_entry[entry["id"]].append(item)
    for entry_id, vat_items in by_entry.items():
        entry = ctx.data.get("journal_entries", entry_id)
        items = ctx.data.items_by_entry[entry_id]
        vat = sum(cents(i["real_debit"]) - cents(i["real_credit"]) for i in vat_items)
        number = lambda i: ctx.data.account_number(i["account_id"]) or ""  # noqa: E731
        targets = [i for i in items if number(i).startswith("6")] or \
                  [i for i in items if not number(i).startswith(("40", "41", "4456"))]
        if not targets:
            raise ImportFailure(f"{entry['number']} : TVA sans ligne de charge où l'intégrer.")
        weights = [abs(cents(i["real_debit"]) - cents(i["real_credit"])) for i in targets]
        total = sum(weights) or len(targets)
        shares = [vat * (w or 1) // total for w in weights]
        shares[weights.index(max(weights))] += vat - sum(shares)
        for item in vat_items:
            deltas[item["id"]] -= cents(item["real_debit"]) - cents(item["real_credit"])
            ctx.absorbed.add(item["id"])
        for item, share in zip(targets, shares):
            deltas[item["id"]] += share
        if vat:
            ctx.vat_corrections.append((entry["number"], vat))
    return deltas


def step_entries(ctx: Context) -> None:
    data = ctx.data
    ctx.deltas = Counter(_vat_plan(ctx))
    confirmed = defaultdict(list)
    for entry in data.entries():
        code = data.journal_code(entry["journal_id"])
        rows, kept = [], []
        for item in data.items_by_entry[entry["id"]]:
            signed = cents(item["real_debit"]) - cents(item["real_credit"]) + ctx.deltas[item["id"]]
            number = data.account_number(item["account_id"])
            if item["id"] in ctx.absorbed and signed == 0:
                continue  # ligne de TVA d'achat absorbée dans la charge (ou TVA nulle)
            if number not in ctx.accounts:
                raise ImportFailure(f"{entry['number']} : compte {number} sans correspondance.")
            rows.append({"account_id": ctx.accounts[number].id, "label": (item.get("name") or "")[:300],
                         "debit_cents": max(signed, 0), "credit_cents": max(-signed, 0)})
            kept.append(item["id"])
        fy = ctx.years[entry["financial_year_id"]]
        opening = code == "RG"
        reference = (entry.get("reference_number") or entry["number"] or "")[:50] or None
        created = post_entry(fy.id, ctx.journals[map_journal(code)].id, day(entry["printed_on"]),
                             (entry.get("name") or entry["number"] or "")[:500], rows,
                             source=SOURCE_OPENING if opening else SOURCE_EKYLIBRE, source_ref=entry["number"],
                             reference=reference, commit=False)
        ctx.entries[entry["id"]] = created
        for item_id, line in zip(kept, sorted(created.lines, key=lambda l: l.id)):
            ctx.lines[item_id] = line
        if entry.get("state") in ("confirmed", "closed"):
            confirmed[fy.id].append(created)
        ctx.stats["entries"] += 1
    for fy_id, entries in confirmed.items():
        validation.validate(db.session.get(FiscalYear, fy_id), entries, "import", until=ctx.data.until)
        ctx.stats["validated"] += len(entries)


# ------------------------------------------------------------------ E7 lettrage


def step_lettering(ctx: Context) -> None:
    groups = defaultdict(list)
    for item_id, line in ctx.lines.items():
        item = ctx.data.get("journal_entry_items", item_id)
        if item.get("letter"):
            groups[(line.account_id, item["letter"].rstrip("*"))].append(line)
    for (account_id, code), lines in sorted(groups.items(), key=lambda g: (g[0][0], g[0][1])):
        account = db.session.get(Account, account_id)
        if len(lines) < 2:
            ctx.stats["letterings_single_line"] += 1
            ctx.notes.append(f"Lettre {code} du compte {account.code} sur une seule ligne dans Ekylibre : non reprise.")
            continue
        if not account.lettrable:  # compte lettré dans Ekylibre (51101000…) : rendu lettrable
            account.lettrable = True
            ctx.notes.append(f"Compte {account.code} rendu lettrable (lettré dans Ekylibre).")
            db.session.flush()
        item = lettering.letter(lines, origin="import")
        wanted = code.lower() if item.partial else code.upper()
        if not Lettering.query.filter(Lettering.account_id == account_id, Lettering.code == wanted[:6],
                                      Lettering.id != item.id).first():
            item.code = wanted[:6]
        ctx.stats["letterings"] += 1
        ctx.stats["letterings_partial"] += int(item.partial)
    db.session.flush()


# ------------------------------------------------------------------ contrôle des balances


def compare_balances(ctx: Context) -> list[str]:
    """Balance Lyvre par compte = balance Ekylibre de la période corrigée (TVA) ; écarts inexpliqués."""
    expected = Counter()
    for entry in ctx.data.entries():
        for item in ctx.data.items_by_entry[entry["id"]]:
            target = ctx.accounts.get(ctx.data.account_number(item["account_id"]))
            if target is not None:
                expected[target.code] += cents(item["real_debit"]) - cents(item["real_credit"]) + ctx.deltas[item["id"]]
    from app.models import JournalLine
    actual = Counter()
    rows = (db.session.query(Account.code, db.func.sum(JournalLine.debit_cents - JournalLine.credit_cents))
            .join(JournalLine, JournalLine.account_id == Account.id).group_by(Account.code).all())
    for code, value in rows:
        actual[code] = value or 0
    return [f"{code} : attendu {expected[code] / 100:.2f} €, Lyvre {actual[code] / 100:.2f} €"
            for code in sorted(set(expected) | set(actual)) if expected[code] != actual[code]]


# ------------------------------------------------------------------ E4 banque


def step_bank(ctx: Context) -> None:
    data = ctx.data
    for cash in data.rows["cashes"]:
        if cash.get("nature") != "bank_account":
            continue
        account = ctx.accounts.get(data.account_number(cash["main_account_id"]))
        if account is None:
            continue
        bank = BankAccount(label=cash["name"][:100], iban=(cash.get("iban") or "").replace(" ", "")[:34] or None,
                           kind="bank", account_id=account.id)
        db.session.add(bank)
        db.session.flush()
        ctx.bank_accounts[cash["id"]] = bank
        statements = {s["id"] for s in data.rows["bank_statements"] if s["cash_id"] == cash["id"]}
        for item in data.statement_items():
            if item["bank_statement_id"] not in statements:
                continue
            amount = cents(item["credit"]) - cents(item["debit"])
            txn = BankTransaction(bank_account_id=bank.id, fitid=f"EKY-{item['id']}", transaction_date=day(item["transfered_on"]),
                                  amount_cents=amount, label=(item.get("name") or "")[:500], source="ekylibre",
                                  reconciled=False, is_reversed=False)
            entity = ctx.entities.get(item.get("entity_id"))
            if entity is not None:
                txn.entity_id = entity.id
            db.session.add(txn)
            db.session.flush()
            ctx.transactions[item["id"]] = txn
            entry = ctx.entries.get(item.get("journal_entry_id"))
            line = next((l for l in entry.lines if l.account_id == account.id
                         and l.debit_cents - l.credit_cents == amount and l.bank_transaction is None), None) if entry else None
            if line is None:
                ctx.notes.append(f"Ligne de relevé du {item['transfered_on']} « {item.get('name')} » ({amount / 100:.2f} €) "
                                 "sans écriture rapprochable.")
                continue
            txn.journal_line_id, txn.reconciled = line.id, True
            ctx.stats["bank_reconciled"] += 1
        ctx.stats["bank_transactions"] += len([t for t in ctx.transactions.values() if t.bank_account_id == bank.id])
    db.session.flush()


# ------------------------------------------------------------------ E5 achats


def _associate_for_cash(ctx: Context, cash_id) -> Associate | None:
    cash = ctx.data.get("cashes", cash_id)
    account = ctx.accounts.get(ctx.data.account_number(cash.get("main_account_id"))) if cash else None
    return Associate.query.filter_by(account_id=account.id).first() if account else None


def _transaction_of(ctx: Context, eky_entry_id):
    item = ctx.data.statement_item_for(eky_entry_id)
    return ctx.transactions.get(item["id"]) if item else None


def step_purchases(ctx: Context) -> None:
    data = ctx.data
    payments_by_affair = defaultdict(list)
    for payment in data.rows["outgoing_payments"]:
        if payment.get("affair_id"):
            payments_by_affair[payment["affair_id"]].append(payment)
    for row in data.purchases():
        entry = ctx.entries.get(row.get("journal_entry_id"))
        entity = ctx.entities.get(row["supplier_id"])
        total = sum(cents(i["amount"]) for i in data.purchase_items[row["id"]])
        credit = total < 0
        purchase = Purchase(source="ekylibre", entity=entity, supplier_name=entity.name if entity else None,
                            invoice_number=(row.get("reference_number") or row.get("number") or "")[:100] or None,
                            issue_date=day(row["invoiced_at"]), due_date=day(row.get("payment_at")),
                            total_cents=abs(total), untaxed_cents=abs(total), tax_cents=0, payable_cents=abs(total),
                            is_credit_note=credit, lines_edited=True,
                            journal_entry_id=entry.id if entry else None,
                            raw_payload=None)
        for position, item in enumerate(data.purchase_items[row["id"]]):
            account = ctx.accounts.get(data.account_number(item.get("account_id")))
            amount = abs(cents(item["amount"]))
            purchase.lines.append(PurchaseLine(position=position, account_id=account.id if account else None,
                                               label=(item.get("label") or "")[:300], untaxed_cents=amount, vat_rate_bp=0,
                                               vat_cents=0, total_cents=amount))
        db.session.add(purchase)
        db.session.flush()
        ctx.purchases[row["id"]] = purchase
        if entry is None:
            ctx.notes.append(f"Achat {row.get('number')} sans écriture reprise.")
        last_paid = None
        for payment in payments_by_affair.get(row.get("affair_id"), []):
            pay_entry = ctx.entries.get(payment.get("journal_entry_id"))
            if pay_entry is None:
                ctx.notes.append(f"Règlement {payment.get('number')} de l'achat {row.get('number')} hors période ou sans écriture.")
                continue
            associate = _associate_for_cash(ctx, payment.get("cash_id"))
            if associate is not None:
                link = PurchasePayment(purchase_id=purchase.id, origin="associate", associate_id=associate.id,
                                       journal_entry_id=pay_entry.id)
            else:
                txn = _transaction_of(ctx, payment.get("journal_entry_id"))
                link = PurchasePayment(purchase_id=purchase.id, origin="match", journal_entry_id=pay_entry.id,
                                       bank_transaction_id=txn.id if txn else None)
            if not PurchasePayment.query.filter_by(purchase_id=purchase.id, journal_entry_id=pay_entry.id).first():
                db.session.add(link)
                ctx.stats["purchase_payments"] += 1
            paid = day(payment.get("paid_at") or payment.get("to_bank_at"))
            last_paid = max(filter(None, (last_paid, paid)), default=None)
        purchase.payment_date = last_paid
        ctx.stats["purchases"] += 1
    affairs = {row.get("affair_id") for row in data.purchases()}
    for payment in data.outgoing_payments():
        if payment.get("affair_id") not in affairs:
            ctx.notes.append(f"Règlement {payment.get('number')} du {payment.get('paid_at', '')[:10]} "
                             f"({cents(payment['amount']) / 100:.2f} €) sans facture d'achat de la période : écriture reprise seule.")
    db.session.flush()


# ------------------------------------------------------------------ E6 ventes


METHODS = {"virement": "transfer", "cheque": "check", "chèque": "check", "especes": "cash", "espèces": "cash"}


def step_sales(ctx: Context) -> None:
    from app.services.sale_settlement import refresh_status
    data = ctx.data
    rows = sorted(data.sales(), key=lambda s: (s.get("invoiced_at") or s.get("created_at"), int(s["id"])))
    for row in rows:
        entity = ctx.entities.get(row["client_id"])
        if entity is None:
            raise ImportFailure(f"Vente {row.get('number')} : client non repris.")
        kind = "quote" if row.get("state") == "estimate" else "credit_note" if row.get("credit") == "t" else "invoice"
        draft = row.get("state") == "draft"  # brouillon Ekylibre : brouillon Lyvre, sans numéro ni écriture
        if draft:
            ctx.notes.append(f"Vente {row.get('number')} en brouillon dans Ekylibre : reprise en brouillon (sans numéro).")
        sale = Sale(kind=kind, status="draft" if draft else "issued", source="ekylibre",
                    number=None if draft else (row.get("number") or "")[:40] or None,
                    entity_id=entity.id, issue_date=day(row.get("invoiced_at") or row.get("created_at")),
                    due_date=day(row.get("payment_at")), untaxed_cents=abs(cents(row.get("pretax_amount"))),
                    total_cents=abs(cents(row.get("amount"))), tax_cents=abs(cents(row.get("amount"))) - abs(cents(row.get("pretax_amount"))),
                    journal_entry_id=ctx.entries[row["journal_entry_id"]].id if row.get("journal_entry_id") in ctx.entries else None)
        if kind == "credit_note" and row.get("credited_sale_id") in ctx.sales:
            sale.invoice_id = ctx.sales[row["credited_sale_id"]].id
        for position, item in enumerate(data.sale_items[row["id"]]):
            account = ctx.accounts.get(data.account_number(item.get("account_id")))
            quantity = abs(float(item.get("quantity") or 1))
            sale.lines.append(SaleLine(position=position, label=(item.get("label") or "Prestation")[:300],
                                       quantity_milli=int(round(quantity * 1000)),
                                       unit_price_cents=abs(cents(item.get("unit_pretax_amount"))),
                                       untaxed_cents=abs(cents(item.get("pretax_amount"))), vat_cents=abs(cents(item.get("amount"))) - abs(cents(item.get("pretax_amount"))),
                                       total_cents=abs(cents(item.get("amount"))), account_id=account.id if account else None))
        db.session.add(sale)
        db.session.flush()
        ctx.sales[row["id"]] = sale
        ctx.stats["sales"] += 1
    # Encaissements par affaire, répartis sur les factures de l'affaire (plus anciennes d'abord).
    modes = {m["id"]: METHODS.get((m.get("name") or "").lower(), "transfer") for m in data.rows["incoming_payment_modes"]}
    by_affair = defaultdict(list)
    for row in rows:
        if row.get("affair_id") and row["id"] in ctx.sales and ctx.sales[row["id"]].kind == "invoice":
            by_affair[row["affair_id"]].append(ctx.sales[row["id"]])
    for payment in data.incoming_payments():
        sales = by_affair.get(payment.get("affair_id"), [])
        entry = ctx.entries.get(payment.get("journal_entry_id"))
        if not sales or entry is None:
            ctx.notes.append(f"Encaissement {payment.get('number')} ({cents(payment['amount']) / 100:.2f} €) non rattaché à une facture reprise.")
            continue
        txn = _transaction_of(ctx, payment.get("journal_entry_id"))
        remaining = cents(payment["amount"])
        for sale in sales:
            due = sale.total_cents - sum(p.amount_cents for p in SalePayment.query.filter_by(sale_id=sale.id))
            share = min(remaining, max(due, 0)) if sale is not sales[-1] else remaining
            if share <= 0:
                continue
            db.session.add(SalePayment(sale_id=sale.id, amount_cents=share, paid_on=day(payment["paid_at"] or payment["to_bank_at"]),
                                       origin="bank" if txn else "manual", method=modes.get(payment.get("mode_id"), "transfer"),
                                       bank_transaction_id=txn.id if txn else None,
                                       bank_account_id=txn.bank_account_id if txn else None, journal_entry_id=entry.id))
            db.session.flush()
            remaining -= share
            ctx.stats["sale_payments"] += 1
            if remaining <= 0:
                break
    for sale in ctx.sales.values():
        if sale.kind == "invoice" and sale.status != "draft":
            refresh_status(sale)
    db.session.flush()


# ------------------------------------------------------------------ E8 immobilisations


def _land_account(ctx: Context) -> Account:
    for code in ("2111", "211"):
        account = Account.query.filter_by(code=code).first()
        if account is not None and not account.is_header:
            return account
    parent = Account.query.filter_by(code="211").first()
    account = Account.query.filter_by(code="211000").first() or Account(code="211000", label="Terrains", account_type="ASSET",
                                                                        parent=parent)
    db.session.add(account)
    db.session.flush()
    return account


LAND_WORDS = ("terre", "terrain", "bois", "foret", "forêt", "pré", "parcelle")


def step_assets(ctx: Context) -> None:
    """Fiches d'immobilisation (EK6) et écriture de reclassement des terrains au premier jour (brouillard)."""
    from app.services import assets as assets_service
    data = ctx.data
    land_total, building = 0, None
    for row in data.rows["fixed_assets"]:
        number = data.account_number(row.get("asset_account_id"))
        account = ctx.accounts.get(number)
        if account is None:
            raise ImportFailure(f"Immobilisation {row['name']} : compte {number} non repris.")
        is_land = any(w in (row["name"] or "").lower() for w in LAND_WORDS)
        target = _land_account(ctx) if is_land and account.code.startswith("213") else account
        amount = cents(row["depreciable_amount"])
        assets_service.save(None, {"label": row["name"], "account_id": target.id, "acquired_on": row["started_on"],
                                   "in_service_date": row["started_on"], "acquisition_cents": amount,
                                   "method": "none" if row.get("depreciation_method") == "none" else "linear",
                                   "duration_months": None if row.get("depreciation_method") == "none" else
                                   int(round(1200 / float(row.get("depreciation_percentage") or 20))),
                                   "notes": "Reprise Ekylibre"})
        ctx.stats["assets"] += 1
        if target.id != account.id:
            land_total += amount
            building = account
    if land_total:
        fy = next(fy for fy in ctx.years.values() if fy.start_date == data.start)
        land = _land_account(ctx)
        entry = post_entry(fy.id, _journal_od().id, data.start, "Reclassement des terrains (Bois, Terres) en 211 — reprise Ekylibre", [
                               {"account_id": land.id, "label": "Terrains", "debit_cents": land_total, "credit_cents": 0},
                               {"account_id": building.id, "label": "Terrains", "debit_cents": 0, "credit_cents": land_total}],
                           source=SOURCE_EKYLIBRE, source_ref="RECLASSEMENT-TERRAINS", commit=False)
        ctx.notes.append(f"Reclassement des terrains : {entry.reference}, {land_total / 100:.2f} € de {building.code} "
                         f"vers {land.code} au {data.start:%d/%m/%Y} (brouillard, à valider avec l'expert-comptable).")


def _journal_od() -> Journal:
    journal = Journal.query.filter_by(code="OD").first()
    if journal is None:
        journal = Journal(code="OD", label="Opérations diverses")
        db.session.add(journal)
        db.session.flush()
    return journal


# ------------------------------------------------------------------ E9 pièces 2026


def step_attachments(ctx: Context, source, year_from: int) -> None:
    """Pièces des factures d'achat à partir de `year_from` (EK5 : 2026), copiées dans le dossier de l'instance."""
    import hashlib
    from pathlib import Path

    from app.services import attachments
    for eky_id, purchase in ctx.purchases.items():
        if purchase.issue_date is None or purchase.issue_date.year < year_from:
            continue
        documents = ctx.data.documents_of("Purchase", eky_id)
        for document in documents[:1]:
            found = source.document_file(document["id"])
            if found is None:
                ctx.notes.append(f"Pièce introuvable dans l'archive pour l'achat {purchase.invoice_number}.")
                continue
            name, content = found
            kind = attachments.sniff(content[:16])
            if kind is None:
                ctx.notes.append(f"Pièce de l'achat {purchase.invoice_number} : type non accepté ({name}).")
                continue
            original = document.get("file_file_name") or f"facture{kind[1]}"
            relative = Path("achats", f"{purchase.issue_date.year:04d}", f"{purchase.issue_date.month:02d}",
                            f"{purchase.id}-{attachments.safe_name(original, kind[1])}")
            target = attachments.instance_dir() / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            purchase.attachment_path, purchase.attachment_name = relative.as_posix(), original[:200]
            purchase.attachment_mime, purchase.attachment_size = kind[0], len(content)
            ctx.attachments.append((purchase.invoice_number, original, hashlib.sha256(content).hexdigest()[:16]))
            ctx.stats["attachments"] += 1
        if len(documents) > 1:
            ctx.notes.append(f"Achat {purchase.invoice_number} : {len(documents)} pièces, la première seule est reprise.")
    db.session.flush()


# ------------------------------------------------------------------ structure (fiche de l'organisation)


def company(data: EkyData) -> dict | None:
    return next((e for e in data.rows["entities"] if e.get("of_company") == "t"), None)


def step_organization(ctx: Context) -> None:
    """Nom, SIREN et adresse de la structure, tirés de la fiche « of_company » d'Ekylibre."""
    from app.models import Organization
    from app.services.ekylibre.mapping import _address
    entity = company(ctx.data)
    if entity is None:
        return
    org = Organization.query.first() or Organization(name=entity["full_name"])
    org.name = (entity.get("full_name") or org.name)[:200]
    siret = (entity.get("siret_number") or "").replace(" ", "")
    if len(siret) >= 9 and not org.siren:
        org.siren = siret[:9]
    street, postal, city = _address(ctx.data, entity["id"])
    org.address_line1 = org.address_line1 or street
    org.postal_code = org.postal_code or postal
    org.city = org.city or city
    db.session.add(org)
    db.session.flush()


# ------------------------------------------------------------------ E10 règles d'affectation (EK4)


STOPWORDS = {"PRELEVEMENT", "PRLV", "VIREMENT", "VIR", "EMIS", "INST", "VERS", "WEB", "SEPA", "CB", "CARTE", "FACTURE",
             "FACT", "DE", "DU", "DES", "LA", "LE", "LES", "EN", "VOTRE", "FAVEUR", "REF", "ECHEANCE", "PAIEMENT", "PAR",
             "ET", "A", "AU", "AUX", "POUR", "NO", "N", "SAS", "SARL", "SA", "EURL", "FR"}
DOMINANT_SHARE = 0.6
MIN_OCCURRENCES = 2
MIN_PATTERN = 6  # caractères : un motif plus court attraperait d'autres libellés


def label_pattern(label: str) -> str | None:
    """Partie stable d'un libellé bancaire : majuscules sans accents, sans mots génériques, chiffres,
    dates ni références ; trois premiers mots significatifs."""
    import re
    import unicodedata
    plain = unicodedata.normalize("NFKD", label or "").encode("ascii", "ignore").decode().upper()
    words = [w for w in re.split(r"[^A-Z0-9]+", plain) if w and not any(c.isdigit() for c in w)
             and w not in STOPWORDS and len(w) > 1]
    return " ".join(words[:3]) or None


def _identifiers(ctx: Context, source) -> None:
    """Fournisseur reconnu : SIRET, TVA, IBAN lus dans les pièces, ajoutés aux fiches s'ils y manquent."""
    from app.services import invoice_reader
    org = company(ctx.data)
    own_siren = ((org or {}).get("siret_number") or "").replace(" ", "")[:9]
    own_ibans = [(c.get("iban") or "").replace(" ", "") for c in ctx.data.rows["cashes"] if c.get("iban")]
    found = defaultdict(lambda: defaultdict(Counter))
    for row in ctx.data.purchases():
        entity = ctx.entities.get(row["supplier_id"])
        if entity is None:
            continue
        for document in ctx.data.documents_of("Purchase", row["id"]):
            text = document.get("file_content_text") or ""
            if not text.strip():
                continue
            ext = invoice_reader.parse_text(text, ignore_ibans=own_ibans, ignore_sirens=[own_siren])
            for name, valid in (("siret", invoice_reader.valid_siret), ("vat_number", invoice_reader.valid_fr_vat),
                                ("iban", invoice_reader.valid_iban)):
                value = ext.value(name)
                if value and valid(value):
                    found[entity.id][name][value] += 1
    owners = defaultdict(set)  # identifiant → fournisseurs où il est lu (intermédiaire, plateforme…)
    for entity_id, fields in found.items():
        for name, values in fields.items():
            for value in values:
                owners[(name, value)].add(entity_id)
    for entity_id, fields in found.items():
        entity = db.session.get(Entity, entity_id)
        for name, values in fields.items():
            shared = [v for v in values if len(owners[(name, v)]) > 1]
            for value in shared:
                ctx.notes.append(f"{name} {value} lu dans les pièces de plusieurs fournisseurs : non retenu pour {entity.name}.")
                del values[value]
            if not values:
                continue
            if len(values) > 1:
                ctx.notes.append(f"{entity.name} : plusieurs {name} lus dans les pièces ({', '.join(values)}) : rien n'est écrit.")
                continue
            (value,) = values
            current = getattr(entity, name)
            if current and current != value:
                ctx.notes.append(f"{entity.name} : {name} de la fiche ({current}) différent de la pièce ({value}) : fiche gardée.")
            elif not current:
                setattr(entity, name, value[:34])
                ctx.stats[f"rules_{name}"] += 1
                ctx.rules.append((entity.name, name, value))


def _products(ctx: Context) -> dict[int, Account]:
    """Compte par fournisseur : produit du catalogue par défaut (compte unique ou dominant ≥ 60 %)."""
    associates = {a.entity_id for a in Associate.query.all()}
    per_supplier = defaultdict(Counter)
    for eky_id, purchase in ctx.purchases.items():
        if purchase.entity_id is None:
            continue
        for line in purchase.lines:
            if line.account_id:
                per_supplier[purchase.entity_id][line.account_id] += 1
    chosen = {}
    for entity_id, counts in per_supplier.items():
        entity = db.session.get(Entity, entity_id)
        account_id, count = counts.most_common(1)[0]
        if entity_id in associates:
            ctx.notes.append(f"{entity.name} : associé, pas de compte par défaut.")
            continue
        if count / sum(counts.values()) < DOMINANT_SHARE:
            ctx.notes.append(f"{entity.name} : comptes trop variés ({len(counts)}), pas de compte par défaut.")
            continue
        account = db.session.get(Account, account_id)
        name = f"{account.label} ({account.code})"[:200]
        product = Product.query.filter_by(name=name).first()
        if product is None:
            product = Product(name=name, kind="purchase", purchase_account_id=account.id, nature="services")
            db.session.add(product)
            db.session.flush()
            ctx.stats["rules_products"] += 1
        if entity.default_product_id is None:
            entity.default_product_id = product.id
            ctx.stats["rules_default_product"] += 1
            ctx.rules.append((entity.name, "compte par défaut", account.code))
        chosen[entity_id] = account
    return chosen


def _bank_rules(ctx: Context, accounts: dict[int, Account]) -> None:
    """Règles bancaires : motif de libellé ≥ 2 fois, un seul fournisseur et un seul compte."""
    from app.models import BankTransaction, PurchasePayment
    by_pattern = defaultdict(list)
    for purchase in ctx.purchases.values():
        for payment in PurchasePayment.query.filter_by(purchase_id=purchase.id, origin="match"):
            txn = db.session.get(BankTransaction, payment.bank_transaction_id) if payment.bank_transaction_id else None
            pattern = label_pattern(txn.label) if txn else None
            if pattern:
                by_pattern[pattern].append(purchase)
    position = (db.session.query(db.func.max(Rule.position)).scalar() or 0) + 1
    for pattern, purchases in sorted(by_pattern.items()):
        suppliers = {p.entity_id for p in purchases}
        targets = {accounts[e].code for e in suppliers if e in accounts}
        if len(pattern) < MIN_PATTERN or len(purchases) < MIN_OCCURRENCES or len(suppliers) != 1 or len(targets) != 1:
            reason = ("motif trop court" if len(pattern) < MIN_PATTERN else
                      "une seule occurrence" if len(purchases) < MIN_OCCURRENCES else
                      "plusieurs fournisseurs" if len(suppliers) != 1 else "pas de compte unique")
            ctx.rules_skipped.append((pattern, reason))
            continue
        entity = db.session.get(Entity, next(iter(suppliers)))
        db.session.add(Rule(position=position, name=f"Reprise Ekylibre — {entity.name}"[:200], label_contains=pattern,
                            entity_name=entity.name, entity_type=entity.entity_type, account_code=next(iter(targets)),
                            is_active=True))
        position += 1
        ctx.stats["rules_bank"] += 1
        ctx.rules.append((entity.name, "règle bancaire", f"« {pattern} » → {next(iter(targets))}"))
    db.session.flush()


def step_rules(ctx: Context, source) -> None:
    _identifiers(ctx, source)
    accounts = _products(ctx)
    _bank_rules(ctx, accounts)
    db.session.flush()


def run(data: EkyData, accounts_plan, entities_plan, chart: Chart, source=None, attachments_from: int | None = None) -> Context:
    """Étapes K2-K3 dans la base courante, sans commit (l'appelant valide ou annule le tout)."""
    ctx = Context(data, chart, accounts_plan, entities_plan)
    step_structure(ctx)
    step_organization(ctx)
    step_associates(ctx)
    step_entries(ctx)
    step_lettering(ctx)
    gaps = compare_balances(ctx)
    if gaps:
        raise ImportFailure("Balance différente d'Ekylibre : " + " ; ".join(gaps[:10]))
    step_bank(ctx)
    step_purchases(ctx)
    step_sales(ctx)
    step_assets(ctx)
    if source is not None and attachments_from:
        step_attachments(ctx, source, attachments_from)
    step_rules(ctx, source)
    return ctx
