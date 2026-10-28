"""Saisie des ventes (lot S1) : brouillons de facture et d'avoir, lignes depuis le catalogue,
calcul des totaux. Un brouillon se modifie et se supprime ; une pièce émise, jamais.

Montants : prix unitaire HT en centimes, quantité × 1000, remise et TVA en points de base.
HT d'une ligne = quantité × prix × (1 − remise), arrondi au centime. TVA calculée **par taux** sur
la somme des HT (règle EN 16931), puis répartie sur les lignes du taux (la dernière absorbe
l'arrondi) : le total de la facture et son Factur-X concordent au centime.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.extensions import db
from app.models import Account, Entity, FiscalYear, Product, Project, Sale, SaleLine
from app.models.sale import OPERATION_TYPES, QUOTE_VALIDITY_DAYS
from app.services import catalog

DEFAULT_SALE_ACCOUNTS = ("706", "7060", "70600000", "708", "7088")
UNITS = {"": "", "unite": "unité", "heure": "heure", "jour": "jour", "mois": "mois", "forfait": "forfait",
         "kg": "kg", "m2": "m²"}


class SaleError(ValueError):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def parse_decimal(value, label, field=None, minimum=None) -> Decimal | None:
    text = str(value if value is not None else "").strip().replace(" ", "").replace("\xa0", "") \
        .replace(" ", "").replace(",", ".").rstrip("%").strip()
    if not text:
        return None
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise SaleError(f"{label} invalide : « {value} ».", field) from None
    if minimum is not None and number < minimum:
        raise SaleError(f"{label} invalide : « {value} ».", field)
    return number


def parse_date(value, label, field) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise SaleError(f"{label} invalide.", field) from None


def fiscal_year_for(day: date | None) -> FiscalYear | None:
    if day is None:
        return None
    return FiscalYear.query.filter(FiscalYear.start_date <= day, FiscalYear.end_date >= day).first()


def vat_mode_for(day: date | None) -> str:
    """Mode de TVA de l'exercice : non assujetti (293 B), à l'encaissement ou d'après les débits."""
    fy = fiscal_year_for(day)
    if fy is None or not fy.vat_liable:
        return "none"
    return "receipts" if fy.vat_on_receipts else "debits"


def client_snapshot(entity: Entity) -> dict:
    """Identité du client figée à l'émission (mentions obligatoires)."""
    return {"name": entity.name, "address_line1": entity.address_line1, "address_line2": entity.address_line2,
            "postal_code": entity.postal_code, "city": entity.city, "country": entity.country or "France",
            "siren": entity.siren or (entity.siret or "")[:9] or None, "siret": entity.siret, "vat_number": entity.vat_number,
            "email": entity.email, "person_kind": entity.person_kind}


def default_sale_account() -> Account | None:
    for code in DEFAULT_SALE_ACCOUNTS:
        account = Account.query.filter_by(code=code, is_header=False).first()
        if account is not None:
            return account
    return None


# ------------------------------------------------------------------ calcul

def compute(sale: Sale) -> None:
    """HT des lignes, TVA par taux répartie sur les lignes, totaux de la pièce (sans commit)."""
    from app.services import vat_codes

    exempt = sale.vat_mode == "none"
    by_rate: dict[int, list[SaleLine]] = {}
    for line in sale.lines:
        gross = Decimal(line.quantity_milli) * line.unit_price_cents / 1000
        line.untaxed_cents = _round(gross * (Decimal(10000 - (line.discount_bp or 0)) / 10000))
        # Lot T2 : client de l'UE avec n° de TVA ou client hors UE → pas de TVA française.
        if exempt or (sale.entity is not None and vat_codes.sale_exemption_code(sale, line.nature)):
            line.vat_rate_bp = 0
        by_rate.setdefault(line.vat_rate_bp or 0, []).append(line)
    tax = 0
    for rate, lines in by_rate.items():
        base = sum(line.untaxed_cents for line in lines)
        rate_tax = _round(Decimal(base) * rate / 10000)
        tax += rate_tax
        allocated = 0
        for line in lines[:-1]:
            line.vat_cents = _round(Decimal(line.untaxed_cents) * rate / 10000)
            allocated += line.vat_cents
        lines[-1].vat_cents = rate_tax - allocated
    for line in sale.lines:
        line.total_cents = line.untaxed_cents + line.vat_cents
    sale.untaxed_cents = sum(line.untaxed_cents for line in sale.lines)
    sale.tax_cents = tax
    sale.total_cents = sale.untaxed_cents + tax


# ------------------------------------------------------------------ formulaire

@dataclass
class Header:
    entity: Entity
    issue_date: date
    due_date: date | None
    validity_date: date | None
    service_start: date | None
    service_end: date | None
    operation_type: str
    purchase_order: str | None
    terms: str | None
    header: str | None
    footer: str | None
    vat_regime: str | None = None


def _client(data) -> Entity:
    entity_id = data.get("entity_id")
    if entity_id:
        entity = db.session.get(Entity, int(entity_id)) if str(entity_id).isdigit() else None
        if entity is None:
            raise SaleError("Client introuvable.", "entity_id")
        return entity
    name = str(data.get("new_client_name") or "").strip()[:200]
    if not name:
        raise SaleError("Choisissez le client.", "entity_id")
    existing = Entity.query.filter(db.func.lower(Entity.name) == name.lower()).first()
    if existing is not None:
        return existing
    entity = Entity(name=name, entity_type="CLIENT")
    db.session.add(entity)
    db.session.flush()
    return entity


def parse_header(data: dict) -> Header:
    issue = parse_date(data.get("issue_date"), "Date", "issue_date") or date.today()
    due = parse_date(data.get("due_date"), "Échéance", "due_date")
    if due is not None and due < issue:
        raise SaleError("L'échéance précède la date de la facture.", "due_date")
    validity = parse_date(data.get("validity_date"), "Validité", "validity_date")
    if validity is not None and validity < issue:
        raise SaleError("La date de validité précède la date du devis.", "validity_date")
    start = parse_date(data.get("service_start"), "Début de prestation", "service_start")
    end = parse_date(data.get("service_end"), "Fin de prestation", "service_end")
    if start and end and end < start:
        raise SaleError("La période de prestation est inversée.", "service_end")
    operation = data.get("operation_type") or "services"
    if operation not in OPERATION_TYPES:
        raise SaleError("Nature de l'opération inconnue.", "operation_type")

    def text(key, size=None):
        value = str(data.get(key) or "").strip()
        return (value[:size] if size else value) or None

    return Header(entity=_client(data), issue_date=issue, due_date=due, validity_date=validity,
                  service_start=start, service_end=end,
                  operation_type=operation, purchase_order=text("purchase_order", 100), terms=text("terms"),
                  header=text("header"), footer=text("footer"), vat_regime=_regime(data))


def _regime(data: dict) -> str | None:
    """Régime TVA choisi sur la pièce (lot T2) ; absent : celui du client."""
    from app.services.vat_codes import REGIMES

    value = data.get("vat_regime")
    if value in (None, ""):
        return None
    if value not in REGIMES:
        raise SaleError("Régime TVA inconnu.", "vat_regime")
    return value


def parse_lines(rows) -> list[SaleLine]:
    """Lignes du formulaire ; compte de vente : celui saisi, sinon celui du produit, sinon le compte
    de vente par défaut du plan (706…)."""
    if not isinstance(rows, list):
        raise SaleError("Lignes attendues.", "lines")
    fallback = default_sale_account()
    lines = []
    for index, row in enumerate(rows, start=1):
        label = str(row.get("label") or "").strip()[:300]
        price = parse_decimal(row.get("unit_price"), f"Prix de la ligne {index}", "lines")
        if not label and price is None:
            continue  # ligne vide
        if not label:
            raise SaleError(f"Désignation de la ligne {index} manquante.", "lines")
        quantity = parse_decimal(row.get("quantity"), f"Quantité de la ligne {index}", "lines", Decimal(0))
        discount = parse_decimal(row.get("discount"), f"Remise de la ligne {index}", "lines", Decimal(0))
        if discount is not None and discount > 100:
            raise SaleError(f"Remise de la ligne {index} supérieure à 100 %.", "lines")
        try:
            rate = catalog.parse_rate_bp(row.get("vat_rate"))
        except ValueError as exc:
            raise SaleError(f"Ligne {index} : {exc}", "lines") from None
        product = None
        if row.get("product_id"):
            product = db.session.get(Product, int(row["product_id"])) if str(row["product_id"]).isdigit() else None
        account = None
        code = str(row.get("account_code") or "").strip()
        if code:
            account = Account.query.filter_by(code=code).first()
            if account is None or account.is_header or not code.startswith("7"):
                raise SaleError(f"Ligne {index} : compte de vente « {code} » invalide (compte 7…).", "lines")
        elif product is not None and product.sale_account_id:
            account = product.sale_account
        else:
            account = fallback
        project = None
        if row.get("project_id"):
            project = db.session.get(Project, int(row["project_id"])) if str(row["project_id"]).isdigit() else None
        nature = row.get("nature") or (product.nature if product else "services")
        lines.append(SaleLine(
            position=len(lines), product_id=product.id if product else None, label=label,
            description=str(row.get("description") or "").strip() or None,
            quantity_milli=_round((quantity if quantity is not None else Decimal(1)) * 1000),
            unit=str(row.get("unit") or "").strip()[:20] or None,
            unit_price_cents=_round((price or Decimal(0)) * 100),
            discount_bp=_round((discount or Decimal(0)) * 100),
            vat_rate_bp=rate or 0, account_id=account.id if account else None,
            project_id=project.id if project else None, nature="goods" if nature == "goods" else "services"))
    if not lines:
        raise SaleError("Ajoutez au moins une ligne.", "lines")
    return lines


def _apply(sale: Sale, header: Header, lines: list[SaleLine], settings) -> None:
    sale.entity = header.entity
    sale.issue_date = header.issue_date
    sale.due_date = header.due_date or (header.issue_date + timedelta(days=settings.payment_terms_days or 0)
                                        if sale.kind == "invoice" else None)
    if sale.kind == "quote":
        sale.due_date = None
        sale.validity_date = header.validity_date or header.issue_date + timedelta(days=QUOTE_VALIDITY_DAYS)
    sale.service_start, sale.service_end = header.service_start, header.service_end
    sale.operation_type, sale.purchase_order = header.operation_type, header.purchase_order
    sale.terms, sale.header, sale.footer = header.terms, header.header, header.footer
    sale.vat_mode = vat_mode_for(header.issue_date)
    if sale.kind != "credit_note":  # l'avoir suit sa facture (vat_codes.sale_regime)
        sale.vat_regime = header.vat_regime or getattr(header.entity, "vat_regime", None) or "fr"
    sale.lines = lines
    compute(sale)


def _qonto_emit(data: dict, kind: str) -> bool:
    """Case « Émettre avec Qonto » : retenue seulement si le périmètre Ventes de Qonto est actif."""
    from app.services import external_config

    return bool(data.get("qonto_emit")) and kind in ("invoice", "quote") and external_config.scope_available("qonto", "sales")


def create(data: dict, kind: str = "invoice") -> Sale:
    from app.services import billing

    sale = Sale(kind=kind, status="draft", source="app", qonto_emit=_qonto_emit(data, kind))
    _apply(sale, parse_header(data), parse_lines(data.get("lines")), billing.get())
    db.session.add(sale)
    db.session.commit()
    return sale


def update(sale: Sale, data: dict) -> Sale:
    from app.services import billing

    if sale.status != "draft":
        raise SaleError("Pièce émise : elle ne se modifie plus.", status=409)
    header, lines = parse_header(data), parse_lines(data.get("lines"))
    if sale.kind == "credit_note":
        header.entity = sale.entity  # l'avoir reste au client de sa facture
    elif "qonto_emit" in data:
        sale.qonto_emit = _qonto_emit(data, sale.kind)
    sale.lines.clear()
    db.session.flush()
    _apply(sale, header, lines, billing.get())
    db.session.commit()
    return sale


def delete(sale: Sale) -> None:
    if sale.status != "draft":
        if sale.kind == "quote":
            raise SaleError("Devis émis : il ne se supprime pas (marquez-le refusé).", status=409)
        raise SaleError("Pièce émise : elle ne se supprime pas (passez un avoir).", status=409)
    quote = db.session.get(Sale, sale.quote_id) if sale.quote_id else None
    db.session.delete(sale)
    db.session.flush()
    if quote is not None and quote.status == "invoiced" and not Sale.query.filter_by(kind="invoice", quote_id=quote.id).count():
        quote.status = "accepted"  # brouillon de facture abandonné : le devis redevient accepté
    db.session.commit()


def json_snapshot(entity: Entity) -> str:
    return json.dumps(client_snapshot(entity), ensure_ascii=False)
