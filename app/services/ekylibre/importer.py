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
    Account, Associate, Entity, FiscalYear, Journal, JournalEntry, Lettering, ShareMovement, ShareMovementLine,
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


def run(data: EkyData, accounts_plan, entities_plan, chart: Chart) -> Context:
    """Étapes K2 dans la base courante, sans commit (l'appelant valide ou annule le tout)."""
    ctx = Context(data, chart, accounts_plan, entities_plan)
    step_structure(ctx)
    step_associates(ctx)
    step_entries(ctx)
    step_lettering(ctx)
    gaps = compare_balances(ctx)
    if gaps:
        raise ImportFailure("Balance différente d'Ekylibre : " + " ; ".join(gaps[:10]))
    return ctx
