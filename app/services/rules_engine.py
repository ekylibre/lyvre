import re

from app.extensions import db
from app.models import (
    Account,
    BankTransaction,
    Entity,
    FiscalYear,
    Journal,
    Rule,
)
from app.services import projects, rule_entries
from app.services.ledger import LedgerError, post_entry


class RuleValidationError(ValueError):
    """Raised by validate_rule_data when a form payload is rejected."""


def load_rules():
    """Active rules for the current tenant, ordered by evaluation priority."""
    return (
        db.session.query(Rule)
        .filter(Rule.is_active.is_(True))
        .order_by(Rule.position.asc())
        .all()
    )


def _match_rule(rule, txn):
    label_upper = (txn.label or "").upper()
    label_raw = txn.label or ""

    if rule.label_contains:
        if rule.label_contains.upper() not in label_upper:
            return False

    if rule.label_regex:
        try:
            if not re.search(rule.label_regex, label_raw, re.IGNORECASE):
                return False
        except re.error:
            return False

    if rule.amount_min_cents is not None:
        if txn.amount_cents < rule.amount_min_cents:
            return False

    if rule.amount_max_cents is not None:
        if txn.amount_cents > rule.amount_max_cents:
            return False

    if rule.raw_type:
        if txn.raw_type != rule.raw_type:
            return False

    return True


def _get_or_create_entity(name, entity_type):
    entity = Entity.query.filter_by(name=name).first()
    if not entity:
        entity = Entity(name=name, entity_type=entity_type or "AUTRE")
        db.session.add(entity)
        db.session.flush()
    return entity


def _direction_error(account_code, amount_cents):
    """Message when the account's side contradicts the transaction's direction
    (a 6xx charge on a credit, a 7xx revenue on a debit), else None."""
    if account_code.startswith("6") and amount_cents > 0:
        return (f"Compte « {account_code} » (charge) incompatible avec un encaissement "
                "— règle non appliquée.")
    if account_code.startswith("7") and amount_cents < 0:
        return (f"Compte « {account_code} » (produit) incompatible avec un décaissement "
                "— règle non appliquée.")
    return None


def _counterpart(account_code):
    counterpart = Account.query.filter_by(code=account_code).first()
    if counterpart is None:
        raise LedgerError(f"Compte « {account_code} » introuvable dans le plan comptable.")
    if counterpart.is_header:
        raise LedgerError(f"Compte « {account_code} » est un compte d'en-tête, non utilisable.")
    if not account_code.startswith(("6", "7")):
        raise LedgerError(f"Compte « {account_code} » : seuls les comptes 6xx (charges) et 7xx (produits) "
                          "sont supportés par le moteur de règles.")
    return counterpart


def _post_entry_for_transaction(txn, account_code, description, project_id=None):
    """Create a balanced journal entry for a categorized bank transaction.

    Convention:
      - account_code starts with 6 (expense) → debit 6xx, credit bank
      - account_code starts with 7 (revenue) → debit bank, credit 7xx

    The amount used is abs(amount_cents). The transaction sign is ignored;
    the account prefix drives the direction.
    """
    counterpart = Account.query.filter_by(code=account_code).first()
    if counterpart is None:
        raise LedgerError(f"Compte « {account_code} » introuvable dans le plan comptable.")
    if counterpart.is_header:
        raise LedgerError(f"Compte « {account_code} » est un compte d'en-tête, non utilisable.")

    if account_code.startswith("6"):
        bank_debit, bank_credit = 0, abs(txn.amount_cents)
        cp_debit, cp_credit = abs(txn.amount_cents), 0
    elif account_code.startswith("7"):
        bank_debit, bank_credit = abs(txn.amount_cents), 0
        cp_debit, cp_credit = 0, abs(txn.amount_cents)
    else:
        raise LedgerError(
            f"Compte « {account_code} » : seuls les comptes 6xx (charges) et 7xx (produits) "
            "sont supportés par le moteur de règles."
        )

    fy = FiscalYear.query.filter(
        FiscalYear.start_date <= txn.transaction_date,
        FiscalYear.end_date >= txn.transaction_date,
    ).first()
    if fy is None:
        raise LedgerError(f"Aucun exercice ne couvre la date {txn.transaction_date}.")

    journal = Journal.query.filter_by(code="BQ").first()
    if journal is None:
        raise LedgerError("Journal « BQ » introuvable.")

    bank_gl_id = txn.bank_account.account_id
    label = txn.label or ""

    entry = post_entry(
        fiscal_year_id=fy.id,
        journal_id=journal.id,
        entry_date=txn.transaction_date,
        auto_date=True,  # transaction d'une période verrouillée : première date ouverte (F2)
        description=description or label,
        lines=[
            {"account_id": bank_gl_id, "label": label,
             "debit_cents": bank_debit, "credit_cents": bank_credit},
            {"account_id": counterpart.id, "label": label,
             "debit_cents": cp_debit, "credit_cents": cp_credit, "project_id": project_id},
        ],
        source="QONTO_IMPORT" if txn.source == "qonto" else "OFX_IMPORT",
        source_ref=f"FITID:{txn.fitid}",
    )

    bank_line = next((l for l in entry.lines if l.account_id == bank_gl_id), None)
    if bank_line is None:
        raise LedgerError("Ligne bancaire introuvable dans l'écriture créée.")
    return bank_line


def apply_rules(transactions=None, overwrite=False):
    """Apply rules (from the tenant DB) to bank transactions.

    Each rule may set `account_code`. When present, the matching transaction
    triggers the automatic creation of its entries, and the bank transaction
    is reconciled against the bank-side journal line : in double-entry
    bookkeeping, a document entry (6xx or 7xx against a third-party account,
    the rule's third party or 401000 / 411000) and a lettered settlement
    (third party / bank) — see `rule_entries` ; in simplified bookkeeping, one
    entry bank / 6xx or 7xx.

    Args:
        transactions: list of BankTransaction, or None to process all
            unclassified ones.
        overwrite: if True, re-classify already-categorized transactions.

    Returns:
        dict with keys: matched, posted, skipped, total, errors and
        created_entry_ids (entries generated, e.g. to undo the run).
    """
    rules = load_rules()

    if transactions is None:
        query = BankTransaction.query
        if not overwrite:
            query = query.filter(
                (BankTransaction.category == None)  # noqa: E711
                | (BankTransaction.entity_id == None)
            )
        transactions = query.all()

    matched = 0
    posted = 0
    skipped = 0
    errors = []
    created_entry_ids = []
    # Paiement d'une facture d'achat : réglé par 401 / banque, jamais par une règle.
    from app.services import sale_settlement
    from app.services.purchase_settlement import linked_transaction_ids
    paying_invoices = linked_transaction_ids([t.id for t in transactions])
    paying_invoices |= sale_settlement.linked_transaction_ids([t.id for t in transactions])

    for txn in transactions:
        if txn.is_reversed or txn.id in paying_invoices:  # annulée, ou règlement de facture
            skipped += 1
            continue
        if not overwrite and (txn.category and txn.entity_id):
            skipped += 1
            continue

        matched_rule = next((r for r in rules if _match_rule(r, txn)), None)
        if matched_rule is None:
            skipped += 1
            continue
        # Un sens contraire au compte (charge sur un encaissement…) passerait une
        # écriture fausse : la transaction est laissée telle quelle et signalée.
        direction_error = matched_rule.account_code and _direction_error(
            matched_rule.account_code, txn.amount_cents)
        if direction_error:
            errors.append(f"FITID {txn.fitid}: {direction_error}")
            skipped += 1
            continue

        entity = None
        if matched_rule.entity_name:
            entity = _get_or_create_entity(
                matched_rule.entity_name,
                matched_rule.entity_type or "AUTRE",
            )
            txn.entity_id = entity.id
        if matched_rule.category:
            txn.category = matched_rule.category
        matched += 1

        if matched_rule.account_code and not txn.journal_line_id:
            description = matched_rule.name or matched_rule.category or ""
            try:
                if rule_entries.simple_mode():
                    bank_line = _post_entry_for_transaction(
                        txn, matched_rule.account_code, description, matched_rule.project_id
                    )
                    txn.journal_line_id = bank_line.id
                    txn.reconciled = True
                    created_entry_ids.append(bank_line.entry_id)
                else:
                    counterpart = _counterpart(matched_rule.account_code)
                    document, settlement = rule_entries.post(
                        txn, counterpart, description, matched_rule.project_id, entity)
                    created_entry_ids += [document.id, settlement.id]
                posted += 1
            except LedgerError as e:
                errors.append(f"FITID {txn.fitid}: {e}")

    db.session.commit()
    return {
        "matched": matched,
        "posted": posted,
        "skipped": skipped,
        "total": len(transactions),
        "errors": errors,
        "created_entry_ids": created_entry_ids,
    }


# ---------------------------------------------------------------------------
# Form validation
# ---------------------------------------------------------------------------

VALID_ENTITY_TYPES = {"CLIENT", "FOURNISSEUR", "SALARIE", "ADHERENT", "ORGANISME", "AUTRE"}


def _clean(value):
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _parse_amount_cents(value):
    if value is None or value == "":
        return None
    return int(round(float(value) * 100))


def validate_rule_data(form) -> dict:
    """Validate a CRUD form payload. Returns a dict ready for `Rule(**data)`.

    Raises RuleValidationError with a user-facing message.
    """
    name = _clean(form.get("name"))
    if not name:
        raise RuleValidationError("Le nom est obligatoire.")

    label_contains = _clean(form.get("label_contains"))
    label_regex = _clean(form.get("label_regex"))
    raw_type = _clean(form.get("raw_type"))

    try:
        amount_min_cents = _parse_amount_cents(form.get("amount_min"))
        amount_max_cents = _parse_amount_cents(form.get("amount_max"))
    except (TypeError, ValueError):
        raise RuleValidationError("Montants min/max invalides.")

    if not any([
        label_contains, label_regex, raw_type,
        amount_min_cents is not None, amount_max_cents is not None,
    ]):
        raise RuleValidationError(
            "Au moins une condition doit être renseignée (libellé, montant ou type)."
        )

    if (
        amount_min_cents is not None
        and amount_max_cents is not None
        and amount_min_cents > amount_max_cents
    ):
        raise RuleValidationError("Le montant min doit être ≤ au montant max.")

    if label_regex:
        try:
            re.compile(label_regex)
        except re.error as e:
            raise RuleValidationError(f"Expression régulière invalide : {e}")

    entity_type = _clean(form.get("entity_type"))
    if entity_type and entity_type not in VALID_ENTITY_TYPES:
        raise RuleValidationError(f"Type d'entité invalide : {entity_type}")

    account_code = _clean(form.get("account_code"))
    if account_code:
        if not (account_code.startswith("6") or account_code.startswith("7")):
            raise RuleValidationError(
                "Le code compte doit commencer par 6 (charge) ou 7 (produit)."
            )
        account = Account.query.filter_by(code=account_code).first()
        if account is None:
            raise RuleValidationError(
                f"Compte « {account_code} » introuvable dans le plan comptable."
            )
        if account.is_header:
            raise RuleValidationError(
                f"Compte « {account_code} » est un compte d'en-tête, non utilisable."
            )

    try:
        project = projects.resolve(form.get("project_id"))
    except ValueError as exc:
        raise RuleValidationError(str(exc)) from None
    if project is not None and not account_code:
        raise RuleValidationError("Le projet s'applique à l'écriture générée : renseignez aussi le compte.")

    return {
        "name": name,
        "label_contains": label_contains,
        "label_regex": label_regex,
        "amount_min_cents": amount_min_cents,
        "amount_max_cents": amount_max_cents,
        "raw_type": raw_type,
        "entity_name": _clean(form.get("entity_name")),
        "entity_type": entity_type,
        "category": _clean(form.get("category")),
        "account_code": account_code,
        "project_id": project.id if project else None,
        "is_active": bool(form.get("is_active")),
    }
