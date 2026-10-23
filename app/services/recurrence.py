"""Factures récurrentes (lot S5, claudedocs/design_ventes.md § 2.2, décision V15).

Une récurrence = un modèle (`Sale`, `kind = template` : client, lignes, textes) et un échéancier
(mensuel, trimestriel, annuel ; jour d'échéance ; terme à échoir ou échu ; début, fin). Les
échéances dues sont **préparées en brouillon** à l'ouverture de la liste « À émettre » (pas de tâche
planifiée) ; une période n'est préparée qu'une fois (`sale_occurrences`, unique par période). Les
brouillons s'émettent (et s'envoient) en lot.

Dans une désignation, `{periode}` est remplacé par la période facturée (« octobre 2026 »,
« T4 2026 », « 2026 »).
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Recurrence, Sale, SaleLine, SaleOccurrence
from app.models.sale import FREQUENCIES
from app.services import sale_entry
from app.services.sale_entry import SaleError

MONTHS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
          "novembre", "décembre"]
STEP = {"monthly": 1, "quarterly": 3, "yearly": 12}


def add_months(day: date, months: int, due_day: int | None = None) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    target = due_day or day.day
    return date(year, month + 1, min(target, monthrange(year, month + 1)[1]))


def period_of(rec: Recurrence, due: date) -> tuple[date, date]:
    """Période facturée par l'échéance : à échoir (qui commence) ou échue (qui vient de finir)."""
    step = STEP[rec.frequency]
    if rec.frequency == "monthly":
        start = due.replace(day=1)
    elif rec.frequency == "quarterly":
        start = date(due.year, 3 * ((due.month - 1) // 3) + 1, 1)
    else:
        start = date(due.year, 1, 1)
    if not rec.in_advance:
        start = add_months(start, -step, 1)
    return start, add_months(start, step, 1) - timedelta(days=1)


def period_label(rec: Recurrence, start: date) -> str:
    if rec.frequency == "monthly":
        return f"{MONTHS[start.month - 1]} {start.year}"
    if rec.frequency == "quarterly":
        return f"T{(start.month - 1) // 3 + 1} {start.year}"
    return str(start.year)


def first_due(start: date, due_day: int) -> date:
    candidate = start.replace(day=min(due_day, monthrange(start.year, start.month)[1]))
    return candidate if candidate >= start else add_months(candidate, 1, due_day)


# ------------------------------------------------------------------ saisie

def _schedule(rec: Recurrence, data: dict) -> None:
    frequency = data.get("frequency") or rec.frequency or "monthly"
    if frequency not in FREQUENCIES:
        raise SaleError("Périodicité inconnue.", "frequency")
    try:
        due_day = int(data.get("due_day") or rec.due_day or 1)
    except (TypeError, ValueError):
        due_day = 0
    if not 1 <= due_day <= 28:
        raise SaleError("Jour d'échéance : de 1 à 28.", "due_day")
    start = sale_entry.parse_date(data.get("start_date"), "Début", "start_date") or rec.start_date or date.today()
    end = sale_entry.parse_date(data.get("end_date"), "Fin", "end_date") if "end_date" in data else rec.end_date
    if end and end < start:
        raise SaleError("La fin précède le début.", "end_date")
    changed = (frequency, due_day, start) != (rec.frequency, rec.due_day, rec.start_date)
    rec.frequency, rec.due_day, rec.start_date, rec.end_date = frequency, due_day, start, end
    if "in_advance" in data:
        rec.in_advance = bool(data.get("in_advance"))
    if "qonto_emit" in data:
        rec.qonto_emit = sale_entry._qonto_emit(data, "invoice")
    if "active" in data:
        rec.active = bool(data.get("active"))
    if rec.next_date is None or changed:
        due = first_due(start, due_day)
        prepared = {o.period_start for o in SaleOccurrence.query.filter_by(recurrence_id=rec.id)} if rec.id else set()
        while period_of(rec, due)[0] in prepared:  # échéances déjà préparées : jamais deux fois
            due = add_months(due, STEP[frequency], due_day)
        rec.next_date = due


def _template(rec: Recurrence, data: dict) -> None:
    header = sale_entry.parse_header({**data, "issue_date": data.get("start_date") or date.today().isoformat()})
    lines = sale_entry.parse_lines(data.get("lines"))
    template = rec.template or Sale(kind="template", status="active", source="app")
    template.entity = header.entity
    template.operation_type, template.purchase_order = header.operation_type, header.purchase_order
    template.terms, template.header, template.footer = header.terms, header.header, header.footer
    template.issue_date = header.issue_date
    template.vat_mode = sale_entry.vat_mode_for(header.issue_date)
    template.lines.clear()
    db.session.flush()
    template.lines = lines
    sale_entry.compute(template)
    rec.template = template


def create(data: dict) -> Recurrence:
    label = str(data.get("label") or "").strip()[:200]
    if not label:
        raise SaleError("Libellé obligatoire.", "label")
    rec = Recurrence(label=label, frequency="monthly", due_day=1)
    _template(rec, data)
    _schedule(rec, data)
    db.session.add(rec)
    db.session.commit()
    return rec


def update(rec: Recurrence, data: dict) -> Recurrence:
    if "label" in data:
        label = str(data.get("label") or "").strip()[:200]
        if not label:
            raise SaleError("Libellé obligatoire.", "label")
        rec.label = label
    if "lines" in data:
        _template(rec, data)
    _schedule(rec, data)
    db.session.commit()
    return rec


def delete(rec: Recurrence) -> None:
    """Supprime la récurrence et son modèle ; les factures déjà préparées ou émises restent."""
    Sale.query.filter_by(recurrence_id=rec.id).update({"recurrence_id": None})
    db.session.delete(rec)
    db.session.commit()


# ------------------------------------------------------------------ échéances

def _draft_from(rec: Recurrence, due: date, start: date, end: date, today: date) -> Sale:
    from app.models import Lease

    template = rec.template
    label = period_label(rec, start)
    lease = Lease.query.filter_by(recurrence_id=rec.id).first()
    sale = Sale(kind="invoice", status="draft", source="app", entity=template.entity, recurrence_id=rec.id,
                # Daté du jour de préparation (numérotation chronologique), payable à l'échéance.
                lease_id=lease.id if lease else None, issue_date=today, due_date=max(due, today), service_start=start, service_end=end, operation_type=template.operation_type,
                purchase_order=template.purchase_order, terms=template.terms, header=template.header,
                footer=template.footer, qonto_emit=rec.qonto_emit and sale_entry._qonto_emit({"qonto_emit": True}, "invoice"))
    sale.vat_mode = sale_entry.vat_mode_for(sale.issue_date)
    sale.lines = [SaleLine(position=l.position, product_id=l.product_id, label=l.label.replace("{periode}", label)[:300],
                           description=(l.description or "").replace("{periode}", label) or None,
                           quantity_milli=l.quantity_milli, unit=l.unit, unit_price_cents=l.unit_price_cents,
                           discount_bp=l.discount_bp, vat_rate_bp=l.vat_rate_bp, account_id=l.account_id,
                           project_id=l.project_id, nature=l.nature) for l in template.lines]
    sale_entry.compute(sale)
    return sale


def prepare_due(today: date | None = None) -> int:
    """Prépare en brouillon les échéances arrivées de toutes les récurrences actives ; idempotent."""
    today = today or date.today()
    prepared = 0
    for rec in Recurrence.query.filter_by(active=True).all():
        while rec.next_date <= today and (rec.end_date is None or rec.next_date <= rec.end_date):
            start, end = period_of(rec, rec.next_date)
            try:
                with db.session.begin_nested():
                    occurrence = SaleOccurrence(recurrence_id=rec.id, period_start=start)
                    db.session.add(occurrence)
                    db.session.flush()
                    sale = _draft_from(rec, rec.next_date, start, end, today)
                    db.session.add(sale)
                    db.session.flush()
                    occurrence.sale_id = sale.id
                prepared += 1
            except IntegrityError:
                pass  # période déjà préparée (préparation concurrente)
            rec.next_date = add_months(rec.next_date, STEP[rec.frequency], rec.due_day)
        db.session.commit()
    return prepared


def due_drafts():
    return (Sale.query.filter(Sale.kind == "invoice", Sale.status == "draft", Sale.recurrence_id.isnot(None))
            .order_by(Sale.due_date, Sale.id).all())


def issue_batch(ids, send: bool = False) -> dict:
    """Émet les brouillons choisis (un échec n'arrête pas les autres), puis les envoie si demandé."""
    from app.services import sale_issue

    issued, errors, to_send = 0, [], []
    for sale in Sale.query.filter(Sale.id.in_(list(ids) or [0]), Sale.status == "draft").order_by(Sale.id):
        try:
            sale_issue.issue(sale)
            issued += 1
            to_send.append(sale)
        except SaleError as exc:
            errors.append(f"{sale.entity.name} : {exc.message}")
    sent = {"sent": 0, "errors": []}
    if send and to_send:
        sent = sale_issue.send(to_send)
    return {"issued": issued, "sent": sent["sent"], "errors": errors + sent["errors"]}
