"""Écritures des règles de catégorisation en partie double : toujours par un compte de tiers.

Une transaction bancaire catégorisée par une règle donne **deux écritures lettrées** :
- une écriture « pièce » au journal des achats (charge 6… au débit, tiers au crédit) ou des ventes
  (tiers au débit, produit 7… au crédit), datée de la transaction, source `RULE`, référence
  `RULE:<FITID>` ;
- un **règlement** au journal de banque (tiers / banque), rapproché de la transaction, référence
  `FITID:<FITID>` (comme les écritures de règle d'avant).

Le tiers est celui de la règle s'il a son compte (401NNN, 411NNN), sinon le tiers **par défaut**
401000 « Fournisseurs divers » / 411000 « Clients divers » ; les deux lignes de tiers sont lettrées.
`assign` attribue ensuite un vrai tiers ; l'arrivée de la facture (achats) ou l'encaissement d'une
facture (ventes) remplace les deux écritures par un règlement du tiers (`remove`).

Mode simplifié : inchangé (écriture directe banque / 6… ou 7…, `rules_engine`).
"""
from app.extensions import db
from app.models import Account, BankTransaction, Entity, FiscalYear, Journal, JournalEntry
from app.services.ledger_errors import LedgerError

SOURCE_RULE = "RULE"
RULE_SOURCES = ("QONTO_IMPORT", "OFX_IMPORT")
DEFAULTS = {"supplier": ("401000", "Fournisseurs divers", "401"), "customer": ("411000", "Clients divers", "411")}
JOURNALS = {"supplier": ("AC", "Achats"), "customer": ("VE", "Ventes")}


def _journal(code: str, label: str) -> Journal:
    journal = Journal.query.filter_by(code=code).first()
    if journal is None:
        journal = Journal(code=code, label=label)
        db.session.add(journal)
        db.session.flush()
    return journal


def default_account(side: str) -> Account:
    """401000 / 411000, créés au besoin sous 401 / 411 (lettrables)."""
    code, label, parent_code = DEFAULTS[side]
    account = Account.query.filter_by(code=code).first()
    if account is None:
        parent = Account.query.filter_by(code=parent_code).first()
        account = Account(code=code, label=label, account_type="TIERS", parent=parent, lettrable=True)
        db.session.add(account)
        db.session.flush()
    elif account.is_header:
        raise LedgerError(f"Le compte {code} est un compte de regroupement : tiers par défaut impossible.")
    return account


def tiers_account(entity: Entity | None, side: str) -> Account:
    """Compte du tiers s'il en a un pour ce côté, sinon le tiers par défaut."""
    code = None
    if entity is not None:
        code = entity.account_code if side == "supplier" else entity.customer_account_code
    account = Account.query.filter_by(code=code).first() if code else None
    return account if account is not None and not account.is_header else default_account(side)


def simple_mode() -> bool:
    try:
        from flask import g
        instance = getattr(g, "current_instance", None)
    except RuntimeError:
        return False
    return getattr(instance, "bookkeeping", "double") == "simple"


def post(txn: BankTransaction, counterpart: Account, description: str, project_id=None,
         entity: Entity | None = None) -> tuple[JournalEntry, JournalEntry]:
    """Pièce et règlement d'une transaction catégorisée (sans commit) ; le règlement est rapproché."""
    from app.services import lettering
    from app.services.ledger import post_entry
    expense = counterpart.code.startswith("6")
    side = "supplier" if expense else "customer"
    tiers = tiers_account(entity, side)
    fy = FiscalYear.query.filter(FiscalYear.start_date <= txn.transaction_date,
                                 FiscalYear.end_date >= txn.transaction_date).first()
    if fy is None:
        raise LedgerError(f"Aucun exercice ne couvre la date {txn.transaction_date}.")
    amount = abs(txn.amount_cents)
    label = txn.label or description or ""
    text = (description or label)[:500]
    document_lines = [
        {"account_id": counterpart.id, "label": label[:300], "debit_cents": amount if expense else 0,
         "credit_cents": 0 if expense else amount, "project_id": project_id},
        {"account_id": tiers.id, "label": label[:300], "debit_cents": 0 if expense else amount,
         "credit_cents": amount if expense else 0},
    ]
    document = post_entry(fy.id, _journal(*JOURNALS[side]).id, txn.transaction_date, text, document_lines,
                          source=SOURCE_RULE, source_ref=f"RULE:{txn.fitid}", commit=False, auto_date=True)
    bank_account_id = txn.bank_account.account_id
    settlement = post_entry(fy.id, _journal("BQ", "Banque").id, txn.transaction_date, text, [
        {"account_id": tiers.id, "label": label[:300], "debit_cents": amount if expense else 0,
         "credit_cents": 0 if expense else amount},
        {"account_id": bank_account_id, "label": label[:300], "debit_cents": 0 if expense else amount,
         "credit_cents": amount if expense else 0},
    ], source="QONTO_IMPORT" if txn.source == "qonto" else "OFX_IMPORT", source_ref=f"FITID:{txn.fitid}",
        commit=False, auto_date=True)
    bank_line = next(l for l in settlement.lines if l.account_id == bank_account_id)
    txn.journal_line_id, txn.reconciled = bank_line.id, True
    db.session.flush()
    tiers_lines = [l for l in (*document.lines, *settlement.lines) if l.account_id == tiers.id]
    if tiers.lettrable and len(tiers_lines) == 2:
        lettering.letter(tiers_lines, origin="auto")
    return document, settlement


def document_of(txn: BankTransaction) -> JournalEntry | None:
    """Pièce de règle (charge ou produit / tiers) d'une transaction, s'il y en a une ; une pièce validée
    puis contrepassée (tiers attribué, facture arrivée) garde sa référence mais ne compte plus."""
    from app.services.ledger import reversed_entry_ids
    return (JournalEntry.query.filter_by(source=SOURCE_RULE, source_ref=f"RULE:{txn.fitid}")
            .filter(JournalEntry.id.notin_(reversed_entry_ids())).order_by(JournalEntry.id.desc()).first())


def is_rule_entry(entry: JournalEntry, txn: BankTransaction, prefixes=("6", "401")) -> bool:
    """Écriture de règle de la transaction : règlement tiers / banque (pièce de règle à côté), ou forme
    d'avant (banque / 6… ou 7… directement). `prefixes` : comptes admis en face de la banque."""
    if entry.source not in RULE_SOURCES or entry.source_ref != f"FITID:{txn.fitid}":
        return False
    codes = [line.account.code for line in entry.lines]
    return len(codes) == 2 and any(code.startswith(prefixes) for code in codes)


def remove(txn: BankTransaction, settlement: JournalEntry) -> None:
    """Retire le règlement de règle et sa pièce (supprimés en brouillard, contrepassés si validés) ;
    la transaction redevient libre (sans commit)."""
    from app.services import lettering
    from app.services.ledger import remove_entry
    txn.journal_line_id, txn.reconciled = None, False
    document = document_of(txn)
    for entry in (settlement, document):
        if entry is None:
            continue
        if entry.fiscal_year.closed:
            raise LedgerError("Exercice clôturé : l'écriture de règle ne peut pas être remplacée.")
        if not entry.is_validated:
            lettering.release([l.id for l in entry.lines])
        remove_entry(entry)
    db.session.flush()


def assign(txn: BankTransaction, entity: Entity) -> tuple[JournalEntry, JournalEntry]:
    """Attribue un vrai tiers aux écritures de règle d'une transaction : les deux écritures sont
    retirées (contrepassées si validées) et repassées sur le compte du tiers, créé au besoin (sans commit)."""
    settlement = txn.journal_line.entry if txn.journal_line is not None else None
    document = document_of(txn)
    if settlement is None or document is None or not is_rule_entry(settlement, txn, ("401", "411")):
        raise LedgerError("Cette transaction n'a pas d'écritures de règle à attribuer.")
    counterpart = next(l.account for l in document.lines if l.account.code.startswith(("6", "7")))
    side = "supplier" if counterpart.code.startswith("6") else "customer"
    if side == "supplier" and not entity.account_code:
        from app.services.purchase_posting import supplier_account
        supplier_account(entity)
    if side == "customer" and not entity.customer_account_code:
        from app.services.sale_posting import customer_account
        customer_account(entity)
    project_id = next((l.project_id for l in document.lines if l.account_id == counterpart.id), None)
    remove(txn, settlement)
    txn.entity_id = entity.id
    return post(txn, counterpart, document.description, project_id, entity)
