"""Comptabilisation des factures d'achat en engagement.

État d'une facture (`purchase_state`) : masquée, à compléter (avec les motifs),
prête ou comptabilisée. Une facture prête est comptabilisée automatiquement
(`post_ready`) au journal AC, à sa date :

    débit  compte de chaque ligne   HT (exercice soumis à TVA) ou TTC (non soumis)
    débit  44566 / 4456             TVA (exercice soumis à TVA)
    crédit 401xxx du fournisseur    TTC

Un avoir produit l'écriture inverse. Le compte 401xxx est celui de la fiche du
fournisseur (`Entity.account_code`, convention 401NNN) ; il est créé dans le plan
s'il n'existe pas, et un fournisseur sans code reçoit le suivant libre.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models import Account, Entity, FiscalYear, Journal, Product, Purchase, PurchaseLine
from app.services import catalog, projects
from app.services.ledger import LedgerError, delete_entries, post_entry

STATE_LABELS = {
    "hidden": "Masquée",
    "to_complete": "À compléter",
    "ready": "Prête",
    "posted": "Comptabilisée",
}
VAT_ACCOUNTS = ("44566", "4456")
SUPPLIER_PARENT = "401"
SUPPLIER_CODE = re.compile(r"^401(\d{3})$")


@dataclass
class State:
    code: str
    reasons: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return STATE_LABELS[self.code]


# ------------------------------------------------------------------ comptes

def fiscal_year_for(day) -> FiscalYear | None:
    if day is None:
        return None
    return (FiscalYear.query
            .filter(FiscalYear.start_date <= day, FiscalYear.end_date >= day)
            .order_by(FiscalYear.start_date.desc()).first())


def vat_account() -> Account | None:
    for code in VAT_ACCOUNTS:
        account = Account.query.filter_by(code=code, is_header=False).first()
        if account is not None:
            return account
    return None


def next_supplier_code() -> str:
    """Prochain 401NNN libre (comptes du plan et codes des fiches)."""
    codes = [c for (c,) in db.session.query(Account.code).filter(Account.code.like("401%"))]
    codes += [c for (c,) in db.session.query(Entity.account_code)
              .filter(Entity.account_code.like("401%"))]
    numbers = [int(m.group(1)) for m in map(SUPPLIER_CODE.match, codes) if m]
    return f"401{max(numbers, default=0) + 1:03d}"


def supplier_account_problem(entity: Entity) -> str | None:
    code = entity.account_code
    if code and not code.startswith("40"):
        return f"Le compte de « {entity.name} » ({code}) n'est pas un compte fournisseur (40…)."
    if code:
        account = Account.query.filter_by(code=code).first()
        if account is not None and account.is_header:
            return f"Le compte de « {entity.name} » ({code}) est un compte d'en-tête."
    return None


def supplier_account(entity: Entity) -> Account:
    """Compte 401xxx du fournisseur, créé (et noté sur la fiche) au besoin ; sans commit."""
    problem = supplier_account_problem(entity)
    if problem:
        raise LedgerError(problem)
    if not entity.account_code:
        entity.account_code = next_supplier_code()
    account = Account.query.filter_by(code=entity.account_code).first()
    if account is None:
        parent = Account.query.filter_by(code=SUPPLIER_PARENT).first()
        account = Account(code=entity.account_code, label=entity.name[:255], account_type="TIERS",
                          parent_id=parent.id if parent else None)
        db.session.add(account)
        db.session.flush()
    return account


# ------------------------------------------------------------------ état

def purchase_state(p: Purchase) -> State:
    if p.journal_entry_id is not None:
        return State("posted")
    if p.is_hidden:
        return State("hidden")
    reasons = []
    if p.currency != "EUR":
        reasons.append(f"Devise {p.currency} non gérée.")
    if p.entity is None:
        reasons.append("Fournisseur à rattacher.")
    else:
        problem = supplier_account_problem(p.entity)
        if problem:
            reasons.append(problem)
    fy = fiscal_year_for(p.issue_date)
    if p.issue_date is None:
        reasons.append("Date de facture manquante.")
    elif fy is None:
        reasons.append(f"Aucun exercice ne couvre le {p.issue_date.strftime('%d/%m/%Y')}.")
    elif fy.closed:
        reasons.append(f"L'exercice « {fy.label} » est clôturé.")
    if not p.lines:
        reasons.append("Aucune ligne.")
    if any(line.account is None or line.account.is_header for line in p.lines):
        reasons.append("Ligne sans compte de charge.")
    if fy is not None and fy.vat_liable:
        if any(line.vat_rate_bp is None for line in p.lines):
            reasons.append("Taux de TVA à confirmer.")
        if any(line.vat_cents for line in p.lines) and vat_account() is None:
            reasons.append("Compte de TVA déductible (44566 ou 4456) absent du plan.")
    lines_total = sum(line.total_cents for line in p.lines)
    if p.lines and lines_total != p.total_cents:
        reasons.append(f"Total des lignes ({_euros(lines_total)}) ≠ TTC ({_euros(p.total_cents)}).")
    return State("to_complete", reasons) if reasons else State("ready")


def _euros(cents) -> str:
    return f"{cents / 100:,.2f} €".replace(",", " ").replace(".", ",")


# ------------------------------------------------------------------ écriture

def _journal() -> Journal:
    journal = Journal.query.filter_by(code="AC").first()
    if journal is None:
        journal = Journal(code="AC", label="Achats")
        db.session.add(journal)
        db.session.flush()
    return journal


def entry_lines(p: Purchase, fy: FiscalYear, supplier: Account) -> list[dict]:
    """Lignes de l'écriture AC (sens d'une facture ; inversées pour un avoir)."""
    label = f"{p.entity.name} — {p.invoice_number or 'sans numéro'}"[:255]
    debits = []
    for line in p.lines:
        amount = line.untaxed_cents if fy.vat_liable else line.total_cents
        if amount:
            debits.append((line.account_id, line.label or label, amount, line.project_id))
    vat = sum(line.vat_cents for line in p.lines) if fy.vat_liable else 0
    if vat:
        debits.append((vat_account().id, f"TVA — {label}", vat, None))
    # Une ligne négative (remise obtenue, 609) passe au crédit.
    lines = [{"account_id": acc, "label": text, "debit_cents": max(amount, 0),
              "credit_cents": max(-amount, 0), "project_id": project_id} for acc, text, amount, project_id in debits]
    lines.append({"account_id": supplier.id, "label": label, "debit_cents": 0,
                  "credit_cents": p.total_cents})
    if p.is_credit_note:
        for line in lines:
            line["debit_cents"], line["credit_cents"] = line["credit_cents"], line["debit_cents"]
    return lines


def post(p: Purchase):
    """Comptabilise une facture prête (sans commit) ; LedgerError sinon."""
    state = purchase_state(p)
    if state.code != "ready":
        raise LedgerError(" ".join(state.reasons) or f"Facture {state.label.lower()}.")
    fy = fiscal_year_for(p.issue_date)
    supplier = supplier_account(p.entity)
    kind = "Avoir" if p.is_credit_note else "Facture"
    entry = post_entry(
        fiscal_year_id=fy.id, journal_id=_journal().id, entry_date=p.issue_date,
        description=f"{kind} {p.invoice_number or ''} — {p.entity.name}".replace("  ", " ")[:500],
        lines=entry_lines(p, fy, supplier), source="PURCHASE", source_ref=f"PURCHASE:{p.id}",
        commit=False, auto_date=True,  # pièce reçue : période verrouillée → première date ouverte (F2)
    )
    p.journal_entry = entry
    p.journal_entry_id = entry.id  # l'état « comptabilisée » se lit avant le flush
    p.review_reason = None
    return entry


def post_ready(purchases) -> dict:
    """Comptabilise les factures prêtes, chacune dans sa propre transaction (commit),
    puis passe les règlements des transactions déjà importées qui les paient."""
    from app.services import purchase_settlement

    result = {"posted": 0, "settled": 0, "errors": []}
    posted = []
    for p in purchases:
        if purchase_state(p).code != "ready":
            continue
        try:
            post(p)
            db.session.commit()
            result["posted"] += 1
            posted.append(p)
        except LedgerError as exc:
            db.session.rollback()
            result["errors"].append(f"Facture {p.invoice_number or p.id} : {exc}")
    if posted:
        settlement = purchase_settlement.settle(purchases=posted)
        result["settled"] = settlement["settled"]
        result["errors"].extend(settlement["errors"])
        manual = [p for p in posted if p.source == "manual"]
        if manual:  # payée hors Qonto : débit unique de même montant
            matching = purchase_settlement.auto_match(manual)
            result["settled"] += matching["settled"]
            result["errors"].extend(matching["errors"])
    return result


def ready_purchases():
    """Factures non comptabilisées et visibles dont l'état est « prête »."""
    candidates = Purchase.query.filter(Purchase.journal_entry_id.is_(None),
                                       Purchase.is_hidden.is_(False)).all()
    return [p for p in candidates if purchase_state(p).code == "ready"]


def count_to_complete() -> int:
    candidates = Purchase.query.filter(Purchase.journal_entry_id.is_(None),
                                       Purchase.is_hidden.is_(False)).all()
    return sum(1 for p in candidates if purchase_state(p).code == "to_complete")


def unpost(p: Purchase) -> None:
    """Supprime l'écriture AC ; une facture Qonto reprend les dernières données Qonto (commit)."""
    if p.journal_entry_id is None:
        raise LedgerError("Cette facture n'est pas comptabilisée.")
    (outcome,) = delete_entries([p.journal_entry_id], reverse_validated=True)
    if outcome["status"] not in ("ok", "reversed"):
        raise LedgerError(outcome["message"])
    db.session.refresh(p)
    p.journal_entry_id = None
    p.review_reason = None
    if p.raw_payload and p.source == "qonto":  # une facture saisie garde sa saisie
        from app.services import purchase_sync
        purchase_sync.apply_payload(p, json.loads(p.raw_payload))
    db.session.commit()


# ------------------------------------------------------------------ suppression

# Statuts Qonto d'une facture validée (approuvée, à payer, payée…) : elle n'est plus supprimable.
QONTO_VALIDATED_STATUSES = {"to_pay", "awaiting_payment", "pending", "scheduled", "paid", "archived"}


def delete_blockers(p: Purchase) -> list[str]:
    """Motifs qui empêchent de supprimer la facture ; liste vide si elle est supprimable."""
    from app.models import PurchasePayment
    from app.services.purchase_sync import STATUS_LABELS

    reasons = []
    if p.qonto_status in QONTO_VALIDATED_STATUSES:
        reasons.append(f"elle est validée dans Qonto (statut « {STATUS_LABELS.get(p.qonto_status, p.qonto_status)} »)")
    if PurchasePayment.query.filter_by(purchase_id=p.id).count():
        reasons.append("elle est liée à un paiement (transaction bancaire ou règlement)")
    linked = bool(p.related_qonto_ids and json.loads(p.related_qonto_ids))
    if not linked and p.qonto_id:
        linked = Purchase.query.filter(Purchase.id != p.id,
                                       Purchase.related_qonto_ids.contains(p.qonto_id)).count() > 0
    if linked:
        reasons.append("elle est liée à une autre facture (avoir)")
    if p.journal_entry is not None and p.journal_entry.fiscal_year.closed:
        reasons.append("son écriture est dans un exercice clôturé")
    return reasons


def delete(p: Purchase) -> str | None:
    """Supprime la facture, son écriture d'achat et sa pièce ; LedgerError si elle est liée.

    Renvoie la référence de l'écriture supprimée, s'il y en avait une. Une facture Qonto
    n'est supprimée que dans l'application.
    """
    from app.services import attachments

    reasons = delete_blockers(p)
    if reasons:
        raise LedgerError("Suppression impossible : " + " ; ".join(reasons) + ".")
    reference = None
    if p.journal_entry_id is not None:
        (outcome,) = delete_entries([p.journal_entry_id], reverse_validated=True)
        if outcome["status"] not in ("ok", "reversed"):
            raise LedgerError(outcome["message"])
        reference = outcome["reference"]
        db.session.refresh(p)
    path = attachments.path_of(p)
    db.session.delete(p)
    db.session.commit()
    if path is not None:
        path.unlink(missing_ok=True)
    return reference


# ------------------------------------------------------------------ lignes saisies

def parse_cents(value) -> int | None:
    """« 1 234,56 » → 123456 ; vide → None ; LedgerError si invalide."""
    text = (value or "").strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not text:
        return None
    try:
        return int((Decimal(text) * 100).quantize(Decimal("1")))
    except InvalidOperation:
        raise LedgerError(f"Montant invalide : « {value} ».") from None


def build_lines(rows) -> list[PurchaseLine]:
    """Lignes à partir des champs du formulaire ; TVA calculée si elle est laissée vide."""
    lines = []
    for row in rows:
        untaxed = parse_cents(row.get("untaxed"))
        if untaxed is None and not (row.get("label") or "").strip():
            continue  # ligne vide
        if untaxed is None:
            raise LedgerError("Chaque ligne doit avoir un montant HT.")
        try:
            rate = catalog.parse_rate_bp(row.get("vat_rate"))
        except ValueError as exc:
            raise LedgerError(str(exc)) from None
        vat = parse_cents(row.get("vat"))
        if vat is None:
            vat = round(untaxed * rate / 10000) if rate is not None else 0
        product = db.session.get(Product, int(row["product_id"])) if row.get("product_id") else None
        code = (row.get("account_code") or "").strip()
        account = Account.query.filter_by(code=code).first() if code else None
        if code and account is None:
            raise LedgerError(f"Compte « {code} » introuvable dans le plan comptable.")
        if account is None and product is not None:
            account = product.purchase_account
        if account is not None and (account.is_header or not account.code.startswith("6")):
            raise LedgerError(f"Compte « {account.code} » : un compte de charge (6…) est attendu.")
        try:
            project = projects.resolve(row.get("project_id"))
        except ValueError as exc:
            raise LedgerError(str(exc)) from None
        lines.append(PurchaseLine(
            position=len(lines), product_id=product.id if product else None,
            account_id=account.id if account else None,
            label=(row.get("label") or (product.name if product else "")).strip()[:300] or None,
            untaxed_cents=untaxed, vat_rate_bp=rate, vat_cents=vat, total_cents=untaxed + vat,
            project_id=project.id if project else None,
        ))
    return lines


def save_lines(p: Purchase, rows) -> dict:
    """Remplace les lignes saisies par le trésorier, puis comptabilise si la facture est prête."""
    if p.journal_entry_id is not None:
        raise LedgerError("Facture comptabilisée : annulez la comptabilisation pour modifier ses lignes.")
    p.lines = build_lines(rows)
    p.lines_edited = True
    catalog.remember_supplier_product(p.entity, p.lines)
    db.session.commit()
    return post_ready([p])
