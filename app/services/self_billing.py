"""Autofactures reçues (lot AG10.c, claudedocs/design_efacturation_agricole.md § 3, AGD27).

Une coopérative, une laiterie ou un négociant facture au nom de l'exploitation, sous mandat de facturation
(type de document 389). Pour Lyvre, c'est une **vente** :
- `analyze(body)` lit le fichier (Factur-X, CII, UBL), contrôle (vendeur = l'exploitation, somme des lignes,
  TVA par taux, totaux, doublon) et propose le client et un compte de vente par ligne ;
- `create(body, …)` enregistre la vente reçue (`self_billed`, `source = received`, numéro du client),
  sans écriture : statut « reçue » ;
- `set_status` : **acceptée** (`fr:205`, la vente est comptabilisée au journal VE), **contestée** (`fr:207`,
  motif obligatoire, rappel dans l'échéancier), **refusée** (`fr:210`, rien n'est comptabilisé) ;
  « encaissée » (`fr:212`) se lit du règlement rapproché. Lyvre n'envoie pas de statut : il affiche le code
  et le motif à reporter dans la plateforme agréée (Q-E1).

Compte de vente proposé par ligne : produit du catalogue de même désignation ; sinon même désignation déjà
reçue de ce client ; sinon production Lexicon reconnue → activité (AG8) → règle « compte → activité ».
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import Account, Activity, AnalyticRule, Entity, Organization, Product, Sale, SaleLine
from app.models.sale import LIFECYCLE
from app.services import einvoice_reader
from app.services.einvoice_reader import EinvoiceError, ReceivedInvoice
from app.services.import_activities import _words, match_production
from app.services.sale_entry import SaleError, fiscal_year_for, json_snapshot, vat_mode_for

FOLDER = "autofactures"
MAX_SIZE = 10 * 1024 * 1024
TRANSITIONS = {"received": ("accepted", "disputed", "refused"), "disputed": ("accepted", "refused")}
GOODS_UNITS = {"kg", "t", "q", "L", "hL", "unité", "m³"}


# ------------------------------------------------------------------ lecture et contrôles

def _read(body: bytes) -> ReceivedInvoice:
    try:
        return einvoice_reader.read(body)
    except EinvoiceError as exc:
        raise SaleError(str(exc), "file") from None


def _organization() -> Organization | None:
    return Organization.query.first()


def find_client(inv: ReceivedInvoice) -> Entity | None:
    buyer = inv.buyer
    if buyer.siren:
        found = Entity.query.filter_by(siren=buyer.siren).order_by(Entity.id).first()
        if found is not None:
            return found
    if buyer.vat_number:
        found = Entity.query.filter_by(vat_number=buyer.vat_number).order_by(Entity.id).first()
        if found is not None:
            return found
    if buyer.name:
        return Entity.query.filter(db.func.lower(Entity.name) == buyer.name.lower()).first()
    return None


def duplicate(entity: Entity | None, number: str) -> Sale | None:
    if entity is None or not number:
        return None
    return Sale.query.filter_by(kind="invoice", entity_id=entity.id, number=number).first()


def checks(inv: ReceivedInvoice) -> tuple[list[str], list[str]]:
    """(problèmes bloquants, avertissements)."""
    problems, warnings = [], []
    org = _organization()
    seller_is_org = bool(org and org.siren and inv.seller.siren == org.siren)
    if inv.credit:
        problems.append("Avoir reçu : l'avoir d'une autofacture n'est pas encore repris, saisissez-le à la main.")
    elif not inv.self_billed and not seller_is_org:
        problems.append("Ce n'est pas une autofacture (type 389) ni une facture émise au nom de l'exploitation : "
                        "une facture d'achat se dépose dans les Achats.")
    if org is None or not org.siren:
        warnings.append("SIREN de l'organisation non renseigné : le vendeur n'est pas contrôlé.")
    elif inv.seller.siren and inv.seller.siren != org.siren:
        problems.append(f"Le vendeur de cette facture (SIREN {inv.seller.siren}) n'est pas l'exploitation "
                        f"(SIREN {org.siren}).")
    elif not inv.seller.siren:
        warnings.append("SIREN du vendeur absent de la facture.")
    if not inv.number:
        problems.append("Numéro de facture absent.")
    if inv.issue_date is None:
        problems.append("Date de facture absente ou illisible.")
    if inv.currency != "EUR":
        problems.append(f"Devise {inv.currency} : seules les factures en euros sont reprises.")
    if not inv.lines:
        problems.append("Aucune ligne de facture.")
    if not inv.buyer.name:
        problems.append("Client (acheteur) sans nom.")
    lines_total = sum(line.net_cents for line in inv.lines)
    if inv.untaxed_cents is not None and lines_total != inv.untaxed_cents:
        problems.append(f"La somme des lignes ({_eur(lines_total)}) ne fait pas le total HT ({_eur(inv.untaxed_cents)}).")
    by_rate: dict[int, int] = {}
    for line in inv.lines:
        by_rate[line.vat_rate_bp] = by_rate.get(line.vat_rate_bp, 0) + line.net_cents
    declared = {t.rate_bp: t for t in inv.taxes}
    for rate, base in sorted(by_rate.items()):
        tax = declared.get(rate)
        if tax is None:
            if rate:
                problems.append(f"Taux de {_pct(rate)} % des lignes absent de la ventilation de TVA.")
            continue
        if tax.base_cents != base:
            problems.append(f"Base de TVA à {_pct(rate)} % : {_eur(tax.base_cents)} déclarés, {_eur(base)} en lignes.")
        expected = int((Decimal(tax.base_cents) * rate / 10000).quantize(Decimal("1")))
        if abs(expected - tax.tax_cents) > 1:
            warnings.append(f"TVA à {_pct(rate)} % : {_eur(tax.tax_cents)} facturés pour {_eur(expected)} calculés.")
    for rate in set(declared) - set(by_rate):
        problems.append(f"Taux de {_pct(rate)} % de la ventilation de TVA sans ligne.")
    tax_total = sum(t.tax_cents for t in inv.taxes)
    if inv.tax_cents is not None and tax_total != inv.tax_cents:
        problems.append(f"TVA par taux ({_eur(tax_total)}) différente du total de TVA ({_eur(inv.tax_cents)}).")
    if inv.total_cents is not None and lines_total + tax_total != inv.total_cents:
        problems.append(f"HT + TVA ({_eur(lines_total + tax_total)}) différent du TTC ({_eur(inv.total_cents)}).")
    if tax_total and vat_mode_for(inv.issue_date) == "none":
        warnings.append("TVA facturée alors que l'exercice n'est pas soumis à la TVA (remboursement forfaitaire, "
                        "franchise) : à contester auprès du client.")
    if inv.payable_cents is not None and inv.total_cents is not None and inv.payable_cents != inv.total_cents:
        warnings.append(f"Net à payer ({_eur(inv.payable_cents)}) différent du TTC : acomptes déjà versés "
                        f"({_eur(inv.total_cents - inv.payable_cents)}) à imputer au règlement.")
    if fiscal_year_for(inv.issue_date) is None and inv.issue_date is not None:
        warnings.append(f"Aucun exercice ne couvre le {inv.issue_date:%d/%m/%Y} : acceptation impossible pour l'instant.")
    return problems, warnings


def _pct(rate_bp: int) -> str:
    return f"{rate_bp / 100:g}".replace(".", ",")


def _eur(cents: int) -> str:
    return f"{cents / 100:,.2f} €".replace(",", " ").replace(".", ",")


# ------------------------------------------------------------------ comptes proposés

def _sale_account(code: str | None) -> Account | None:
    if not code:
        return None
    account = Account.query.filter_by(code=code, is_header=False).first()
    if account is None:
        account = (Account.query.filter(Account.code.like(f"{code}%"), Account.is_header.is_(False))
                   .order_by(Account.code).first())
    return account if account is not None and account.code.startswith("7") else None


def propose_account(label: str, entity: Entity | None) -> tuple[Account | None, str | None]:
    """(compte, origine) : produit du catalogue, désignation déjà reçue du client, activité ; sinon (None, None)."""
    words = _words(label)
    if words:
        for product in Product.query.filter(Product.active.is_(True), Product.kind.in_(("sale", "both")),
                                            Product.sale_account_id.isnot(None)):
            if _words(product.name) == words and product.sale_account and not product.sale_account.is_header:
                return product.sale_account, "product"
        if entity is not None:
            previous = (SaleLine.query.join(Sale).filter(Sale.entity_id == entity.id, Sale.self_billed.is_(True),
                                                         SaleLine.account_id.isnot(None))
                        .order_by(Sale.issue_date.desc(), Sale.id.desc()).limit(200).all())
            for line in previous:
                if _words(line.label) == words:
                    return line.account, "history"
    production = match_production(label)
    if production is not None:
        activity = Activity.query.filter_by(lexicon_reference=production["reference"], archived=False).first()
        if activity is None:
            activity = next((a for a in Activity.query.filter_by(archived=False) if _words(a.name) == _words(production["name"])), None)
        account = activity_account(activity) if activity is not None else None
        if account is not None:
            return account, "activity"
    return None, None


def activity_account(activity: Activity) -> Account | None:
    """Compte de vente de l'activité : celui de sa règle « compte → activité » (préfixe le plus long)."""
    for rule in AnalyticRule.query.filter_by(activity_id=activity.id).order_by(db.func.length(AnalyticRule.account_prefix).desc()):
        account = _sale_account(rule.account_prefix)
        if account is not None:
            return account
    return None


ORIGIN_LABELS = {"product": "produit du catalogue", "history": "déjà reçu de ce client", "activity": "activité"}


# ------------------------------------------------------------------ analyse

def _party(p) -> dict:
    return {"name": p.name, "siren": p.siren, "siret": p.siret, "vat_number": p.vat_number,
            "address_line1": p.address_line1, "postal_code": p.postal_code, "city": p.city, "country": p.country}


def analyze(body: bytes) -> dict:
    inv = _read(body)
    problems, warnings = checks(inv)
    entity = find_client(inv)
    dup = duplicate(entity, inv.number)
    if dup is not None:
        problems.append(f"Doublon : la facture {inv.number} de « {entity.name} » est déjà enregistrée.")
    lines = []
    for index, line in enumerate(inv.lines):
        account, origin = propose_account(line.label, entity)
        lines.append({"index": index, "label": line.label, "kind": line.kind,
                      "quantity": f"{line.quantity.normalize():f}" if line.quantity is not None else "",
                      "unit": line.unit or "", "unit_price": f"{line.unit_price:.4f}".rstrip("0").rstrip(".")
                      if line.unit_price is not None else "", "net_cents": line.net_cents,
                      "vat_rate_bp": line.vat_rate_bp, "account_code": account.code if account else "",
                      "account_origin": ORIGIN_LABELS.get(origin)})
    return {"syntax": inv.syntax, "container": inv.container, "type_code": inv.type_code, "self_billed": inv.self_billed,
            "number": inv.number, "issue_date": inv.issue_date.isoformat() if inv.issue_date else None,
            "due_date": inv.due_date.isoformat() if inv.due_date else None, "seller": _party(inv.seller),
            "buyer": _party(inv.buyer), "client": {"id": entity.id, "name": entity.name} if entity else None,
            "lines": lines, "taxes": [{"rate_bp": t.rate_bp, "base_cents": t.base_cents, "tax_cents": t.tax_cents}
                                      for t in inv.taxes],
            "untaxed_cents": sum(l.net_cents for l in inv.lines), "tax_cents": sum(t.tax_cents for t in inv.taxes),
            "total_cents": inv.total_cents, "payable_cents": inv.payable_cents,
            "notes": [{"subject": s, "text": t} for s, t in inv.notes], "problems": problems, "warnings": warnings}


# ------------------------------------------------------------------ enregistrement

def _client(inv: ReceivedInvoice) -> Entity:
    found = find_client(inv)
    if found is not None:
        return found
    buyer = inv.buyer
    name = buyer.name[:200]
    if Entity.query.filter_by(name=name).first() is not None:
        name = f"{name[:185]} ({buyer.siren or 'reçu'})"
    entity = Entity(name=name, entity_type="CLIENT", siren=buyer.siren, vat_number=buyer.vat_number,
                    address_line1=buyer.address_line1, postal_code=buyer.postal_code, city=buyer.city,
                    country="France" if (buyer.country or "FR") == "FR" else buyer.country, person_kind="company")
    if buyer.siret:
        entity.siret = buyer.siret
    db.session.add(entity)
    db.session.flush()
    return entity


def _account(code: str, index: int) -> Account | None:
    code = str(code or "").strip()
    if not code:
        return None
    account = Account.query.filter_by(code=code).first()
    if account is None or account.is_header or not code.startswith("7"):
        raise SaleError(f"Ligne {index + 1} : compte de vente « {code} » invalide (compte 7…).", "lines")
    return account


def _store(sale: Sale, body: bytes, filename: str) -> None:
    from app.services.attachments import _within, instance_dir
    ext = ".pdf" if body.startswith(b"%PDF-") else ".xml"
    stem = secure_filename(Path(filename or "").stem)[:80] or "autofacture"
    day = sale.issue_date
    relative = Path(FOLDER, f"{day.year:04d}", f"{day.month:02d}", f"{sale.id}-{stem}{ext}")
    target = _within(instance_dir() / relative, instance_dir())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    sale.received_file = relative.as_posix()


def received_path(sale: Sale) -> Path | None:
    from app.services.attachments import AttachmentError, _within, instance_dir
    if not sale.received_file:
        return None
    try:
        path = _within(instance_dir() / sale.received_file, instance_dir())
    except AttachmentError:
        return None
    return path if path.is_file() else None


def create(body: bytes, filename: str, accounts: dict | None = None) -> Sale:
    """Vente reçue (sans écriture) ; `accounts` : {indice de ligne: code du compte de vente}."""
    inv = _read(body)
    problems, _ = checks(inv)
    if problems:
        raise SaleError(problems[0], "file")
    entity = _client(inv)
    if duplicate(entity, inv.number) is not None:
        raise SaleError(f"Doublon : la facture {inv.number} de « {entity.name} » est déjà enregistrée.", "file", 409)
    accounts = accounts or {}
    sale = Sale(kind="invoice", status="draft", source="received", self_billed=True, lifecycle_status="received",
                lifecycle_at=datetime.utcnow(), number=inv.number, entity=entity, issue_date=inv.issue_date,
                due_date=inv.due_date or inv.issue_date, vat_mode=vat_mode_for(inv.issue_date), vat_regime="fr",
                operation_type="goods" if all(l.unit in GOODS_UNITS for l in inv.lines if l.kind == "line") else "services",
                raw_payload=json.dumps({"syntax": inv.syntax, "type_code": inv.type_code,
                                        "notes": inv.notes, "payable_cents": inv.payable_cents}, ensure_ascii=False))
    taxes = {t.rate_bp: t.tax_cents for t in inv.taxes}
    by_rate: dict[int, list[SaleLine]] = {}
    for index, line in enumerate(inv.lines):
        account = _account(accounts.get(str(index)) or accounts.get(index), index)
        if account is None:
            account, _ = propose_account(line.label, entity)
        quantity = line.quantity if line.quantity is not None else Decimal(1)
        unit_price = line.unit_price if line.unit_price is not None else (
            Decimal(line.net_cents) / 100 / quantity if quantity else Decimal(0))
        row = SaleLine(position=index, label=line.label, quantity_milli=int((quantity * 1000).quantize(Decimal("1"))),
                       unit=line.unit, unit_price_cents=int((unit_price * 100).quantize(Decimal("1"))),
                       untaxed_cents=line.net_cents, vat_rate_bp=line.vat_rate_bp,
                       account_id=account.id if account else None,
                       nature="goods" if sale.operation_type == "goods" else "services")
        sale.lines.append(row)
        by_rate.setdefault(line.vat_rate_bp, []).append(row)
    for rate, rows in by_rate.items():  # TVA de la facture répartie sur les lignes du taux, au prorata
        total, base, allocated = taxes.get(rate, 0), sum(r.untaxed_cents for r in rows), 0
        for row in rows[:-1]:
            row.vat_cents = int((Decimal(total) * row.untaxed_cents / base).quantize(Decimal("1"))) if base else 0
            allocated += row.vat_cents
        rows[-1].vat_cents = total - allocated
    for row in sale.lines:
        row.total_cents = row.untaxed_cents + row.vat_cents
    sale.untaxed_cents = sum(r.untaxed_cents for r in sale.lines)
    sale.tax_cents = sum(r.vat_cents for r in sale.lines)
    sale.total_cents = sale.untaxed_cents + sale.tax_cents
    db.session.add(sale)
    db.session.flush()
    _store(sale, body, filename)
    db.session.commit()
    return sale


# ------------------------------------------------------------------ cycle de vie

def lifecycle(sale: Sale) -> str | None:
    """Statut affiché : « encaissée » une fois l'autofacture acceptée et réglée."""
    if not sale.self_billed:
        return None
    if sale.lifecycle_status == "accepted" and sale.status == "paid":
        return "paid"
    return sale.lifecycle_status


def lifecycle_payload(sale: Sale) -> dict | None:
    status = lifecycle(sale)
    if status is None:
        return None
    label, code = LIFECYCLE.get(status, (status, None))
    return {"status": status, "label": label, "code": code, "reason": sale.lifecycle_reason,
            "at": sale.lifecycle_at.isoformat() if sale.lifecycle_at else None,
            "actions": list(TRANSITIONS.get(sale.lifecycle_status, ()))}


def set_status(sale: Sale, status: str, reason: str | None = None, accounts: dict | None = None) -> Sale:
    """Acceptation (écriture VE), contestation (motif), refus ; `accounts` : {id de ligne: code} avant acceptation."""
    from app.services import sale_posting
    from app.services.ledger import LedgerError

    if not sale.self_billed:
        raise SaleError("Cette pièce n'est pas une autofacture reçue.", status=409)
    if status not in TRANSITIONS.get(sale.lifecycle_status, ()):
        raise SaleError(f"Autofacture {LIFECYCLE.get(sale.lifecycle_status, ('',))[0].lower()} : "
                        f"action « {status} » impossible.", "status", 409)
    reason = (reason or "").strip()[:2000] or None
    if status == "disputed" and not reason:
        raise SaleError("Motif de la contestation obligatoire (à reporter dans la plateforme).", "reason")
    for line in sale.lines:
        code = (accounts or {}).get(str(line.id)) or (accounts or {}).get(line.id)
        if code:
            line.account_id = _account(code, line.position).id
    if status == "accepted":
        fy = fiscal_year_for(sale.issue_date)
        if fy is None or fy.closed:
            raise SaleError(f"Aucun exercice ouvert ne couvre le {sale.issue_date:%d/%m/%Y}.", status=409)
        sale.client_snapshot = json_snapshot(sale.entity)
        sale.status, sale.issued_at = "issued", datetime.utcnow()
        try:
            sale_posting.post(sale, fy)
        except LedgerError as exc:
            raise SaleError(str(exc), status=409) from None
    elif status == "refused":
        sale.status = "canceled"
    sale.lifecycle_status, sale.lifecycle_reason, sale.lifecycle_at = status, reason, datetime.utcnow()
    db.session.commit()
    return sale


def disputed():
    return Sale.query.filter_by(self_billed=True, lifecycle_status="disputed").order_by(Sale.issue_date).all()


def agenda_occurrences(start, end) -> list[dict]:
    """Règle `lyvre` de source `self_billing_disputes` : autofactures contestées, à l'échéance de la facture."""
    out = []
    for sale in disputed():
        day = sale.due_date or sale.issue_date
        if day and start <= day <= end:
            out.append({"date": day, "period": f"autofacture {sale.number} — {sale.entity.name}",
                        "lyvre_status": None, "amount_cents": sale.total_cents, "link": f"/sales/{sale.id}"})
    return out
