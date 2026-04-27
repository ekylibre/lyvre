import re
import yaml
from pathlib import Path
from app.extensions import db
from app.models import BankTransaction, Entity, Account, FiscalYear, Journal
from app.services.ledger import post_entry, LedgerError

DEFAULT_RULES_PATH = Path(__file__).parent.parent.parent / "data" / "rules.yml"


def load_rules(path=None):
    rules_path = Path(path) if path else DEFAULT_RULES_PATH
    with open(rules_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("rules", [])


def _match_rule(rule, txn):
    label = (txn.label or "").upper()

    if "label_contains" in rule:
        if rule["label_contains"].upper() not in label:
            return False

    if "label_regex" in rule:
        if not re.search(rule["label_regex"], txn.label or "", re.IGNORECASE):
            return False

    if "amount_min" in rule:
        if txn.amount_cents < int(rule["amount_min"] * 100):
            return False

    if "amount_max" in rule:
        if txn.amount_cents > int(rule["amount_max"] * 100):
            return False

    if "raw_type" in rule:
        if txn.raw_type != rule["raw_type"]:
            return False

    return True


def _get_or_create_entity(name, entity_type):
    entity = Entity.query.filter_by(name=name).first()
    if not entity:
        entity = Entity(name=name, entity_type=entity_type or "AUTRE")
        db.session.add(entity)
        db.session.flush()
    return entity


def _post_entry_for_transaction(txn, account_code, description):
    """Create a balanced journal entry for a categorized bank transaction.

    Convention :
      - account_code commence par 6 (charge) → débit 6xx, crédit compte bancaire
      - account_code commence par 7 (produit) → débit compte bancaire, crédit 7xx

    Le montant utilisé est abs(amount_cents). Le signe de la transaction n'est
    pas pris en compte : c'est le préfixe du compte qui détermine le sens.

    Returns the bank-side JournalLine (to be linked to the BankTransaction)
    or raises LedgerError if posting is impossible.
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
        description=description or label,
        lines=[
            {"account_id": bank_gl_id, "label": label,
             "debit_cents": bank_debit, "credit_cents": bank_credit},
            {"account_id": counterpart.id, "label": label,
             "debit_cents": cp_debit, "credit_cents": cp_credit},
        ],
        source="OFX_IMPORT",
        source_ref=f"FITID:{txn.fitid}",
    )

    bank_line = next((l for l in entry.lines if l.account_id == bank_gl_id), None)
    if bank_line is None:
        raise LedgerError("Ligne bancaire introuvable dans l'écriture créée.")
    return bank_line


def apply_rules(transactions=None, rules_path=None, overwrite=False):
    """Apply YAML rules to bank transactions.

    Each rule may include an `account` field. When present, the matching
    transaction triggers the automatic creation of a balanced journal entry
    (BQ journal, fiscal year derived from transaction date), and the bank
    transaction is reconciled against the bank-side journal line.

    Args:
        transactions: list of BankTransaction, or None to process all unclassified ones
        rules_path: path to YAML file, defaults to data/rules.yml
        overwrite: if True, re-classify already-categorized transactions

    Returns:
        dict with keys: matched, posted, skipped, total, errors
    """
    rules = load_rules(rules_path)

    if transactions is None:
        query = BankTransaction.query
        if not overwrite:
            query = query.filter(
                (BankTransaction.category == None) | (BankTransaction.entity_id == None)
            )
        transactions = query.all()

    matched = 0
    posted = 0
    skipped = 0
    errors = []

    for txn in transactions:
        if not overwrite and (txn.category and txn.entity_id):
            skipped += 1
            continue

        matched_rule = next((r for r in rules if _match_rule(r, txn)), None)
        if matched_rule is None:
            skipped += 1
            continue

        if matched_rule.get("entity"):
            entity = _get_or_create_entity(
                matched_rule["entity"],
                matched_rule.get("entity_type", "AUTRE"),
            )
            txn.entity_id = entity.id
        if matched_rule.get("category"):
            txn.category = matched_rule["category"]
        matched += 1

        account_code = matched_rule.get("account")
        if account_code and not txn.journal_line_id:
            description = matched_rule.get("name", "") or matched_rule.get("category", "")
            try:
                bank_line = _post_entry_for_transaction(txn, str(account_code), description)
                txn.journal_line_id = bank_line.id
                txn.reconciled = True
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
    }
