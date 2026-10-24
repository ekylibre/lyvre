"""Révision des loyers (lot L5, décisions BX14, BF21–BF23).

- Indices : ILC, ILAT et IRL lus à l'INSEE (séries BDM publiques, sans clé, trimestrielles,
  période « 2026-Q2 ») ; indice national des fermages saisi (arrêté annuel, période « 2026 »).
  Une valeur saisie à la main l'emporte sur l'INSEE (correction).
- Révision : à la date prévue (`leases.next_revision_date`), indice de la **même période**
  `revision_months` plus tard (règle usuelle : même trimestre, un ou trois ans après) ; chaque prix
  de ligne × nouvel indice ÷ indice de référence (au centime), facture récurrente mise à jour pour les
  échéances **pas encore préparées**, dépôt de garantie révisé si le bail le prévoit, nouvel indice de
  référence, prochaine date. Indice pas encore publié : révision **en attente**, réessayée à chaque
  passage. Déclenchée avant la préparation des échéances (« À émettre ») et à la demande.
- Un bail signé reste révisable : la révision applique une clause du bail, elle ne le modifie pas.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

import requests

from app.extensions import db
from app.models import Lease, LeaseRevision, RentIndex
from app.services import leases, recurrence

INSEE_SERIES = {"ILC": "001532540", "ILAT": "001617112", "IRL": "001515333"}
INSEE_URL = "https://bdm.insee.fr/series/sdmx/data/SERIES_BDM/{}"
ANNUAL = {"FERMAGES"}
FETCH_EVERY = timedelta(days=1)
TIMEOUT = 10
QUARTER = re.compile(r"^(\d{4})\s*[-\s]?\s*[QT]([1-4])$", re.I)
YEAR = re.compile(r"^(\d{4})$")


class RevisionError(ValueError):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


# ------------------------------------------------------------------ périodes et indices

def normalize_period(code: str, value: str) -> str:
    """« 2025-T2 », « 2025 Q2 » → « 2025-Q2 » ; fermages : « 2025 »."""
    text = (value or "").strip().upper()
    if code in ANNUAL:
        if not YEAR.match(text):
            raise RevisionError("Période de l'indice des fermages : l'année (2025).", "period")
        return text
    match = QUARTER.match(text)
    if not match:
        raise RevisionError("Période trimestrielle attendue : 2025-T2.", "period")
    return f"{match.group(1)}-Q{match.group(2)}"


def shift_period(period: str, months: int) -> str:
    """Même trimestre (ou même année) `months` mois plus tard : 2025-Q2 + 36 → 2028-Q2."""
    years = months // 12
    match = QUARTER.match(period)
    if match:
        return f"{int(match.group(1)) + years}-Q{match.group(2)}"
    return str(int(period) + years)


def label_period(period: str | None) -> str:
    match = QUARTER.match(period or "")
    if match:
        q = int(match.group(2))
        return f"{q}{'er' if q == 1 else 'e'} trimestre {match.group(1)}"
    return period or ""


def value_of(code: str, period: str) -> Decimal | None:
    """Valeur connue (saisie à la main d'abord, sinon INSEE)."""
    rows = RentIndex.query.filter_by(code=code, period=period).all()
    row = next((r for r in rows if r.source == "manual"), None) or next(iter(rows), None)
    return Decimal(row.value) if row is not None else None


def save_value(code: str, period: str, value) -> RentIndex:
    """Saisie (ou correction) d'une valeur ; remplace la valeur INSEE de la même période (commit)."""
    if code not in leases.INDEXES:
        raise RevisionError("Indice inconnu.", "code")
    period = normalize_period(code, period)
    try:
        number = Decimal(str(value).replace(",", ".").strip())
    except Exception:  # noqa: BLE001
        raise RevisionError("Valeur de l'indice invalide.", "value") from None
    if not Decimal(1) <= number <= Decimal(10000):
        raise RevisionError("Valeur de l'indice invalide.", "value")
    row = RentIndex.query.filter_by(code=code, period=period).first() or RentIndex(code=code, period=period)
    row.value, row.source, row.fetched_at = number.quantize(Decimal("0.01")), "manual", datetime.utcnow()
    db.session.add(row)
    db.session.commit()
    return row


def fetch_series(series_id: str) -> list[tuple[str, Decimal]]:
    """Dernières valeurs d'une série BDM de l'INSEE : [(« 2026-Q2 », valeur)]. Remplacé dans les tests."""
    try:
        response = requests.get(INSEE_URL.format(series_id), params={"lastNObservations": 16}, timeout=TIMEOUT)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except (requests.RequestException, ET.ParseError):
        raise RevisionError("L'INSEE ne répond pas : réessayez plus tard ou saisissez l'indice.", status=503) from None
    values = []
    for node in root.iter():
        period, value = node.attrib.get("TIME_PERIOD"), node.attrib.get("OBS_VALUE")
        if period and value and QUARTER.match(period):
            values.append((normalize_period("ILC", period), Decimal(value)))
    return values


def fetch_insee(codes=None) -> int:
    """Enregistre les périodes publiées manquantes (ou changées) des indices INSEE ; nombre de valeurs
    nouvelles. Les valeurs saisies à la main ne sont pas touchées (commit)."""
    added = 0
    for code in codes or INSEE_SERIES:
        for period, value in fetch_series(INSEE_SERIES[code]):
            row = RentIndex.query.filter_by(code=code, period=period).first()
            if row is not None and row.source == "manual":
                continue
            if row is None:
                row = RentIndex(code=code, period=period, source="insee")
                db.session.add(row)
                added += 1
            row.value, row.fetched_at = value.quantize(Decimal("0.01")), datetime.utcnow()
    db.session.commit()
    return added


def last_fetch() -> datetime | None:
    return db.session.query(db.func.max(RentIndex.fetched_at)).filter(RentIndex.source == "insee").scalar()


# ------------------------------------------------------------------ révisions

def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), ROUND_HALF_UP))


def _reference(lease: Lease) -> tuple[str | None, Decimal | None]:
    period = lease.index_reference_period
    value = Decimal(lease.index_reference_value) if lease.index_reference_value is not None else None
    if value is None and period:
        value = value_of(lease.index_code, period)
    return period, value


def _due(today: date) -> list[Lease]:
    return (Lease.query.filter(Lease.status == "active", Lease.active.is_(True), Lease.index_code.isnot(None),
                               Lease.next_revision_date.isnot(None), Lease.next_revision_date <= today)
            .order_by(Lease.id).all())


def revise(lease: Lease) -> LeaseRevision:
    """Révision du bail à sa date prévue : appliquée si l'indice est connu, sinon en attente (sans commit)."""
    due = lease.next_revision_date
    row = LeaseRevision.query.filter_by(lease_id=lease.id, due_date=due).first() or \
        LeaseRevision(lease=lease, due_date=due, index_code=lease.index_code, status="pending")
    old_period, old_value = _reference(lease)
    if not old_period:
        row.new_period, row.note = "?", "Période de l'indice de référence manquante (étape 1 du bail)."
        db.session.add(row)
        return row
    new_period = shift_period(old_period, lease.revision_months or 12)
    new_value = value_of(lease.index_code, new_period)
    row.old_period, row.old_value, row.new_period = old_period, old_value, new_period
    if old_value is None or new_value is None:
        missing = label_period(old_period if old_value is None else new_period)
        row.note = f"Indice {lease.index_code} du {missing} pas encore connu."
        db.session.add(row)
        return row
    ratio = new_value / old_value
    row.new_value, row.old_annual_cents, row.old_deposit_cents = new_value, leases.annual_total(lease), lease.deposit_cents
    for item in lease.items:
        item.unit_price_cents = _round(Decimal(item.unit_price_cents) * ratio)
        item.annual_cents = leases.annual_of(item)
    if lease.revise_deposit and lease.deposit_cents:
        lease.deposit_cents = _round(Decimal(lease.deposit_cents) * ratio)
    leases._sync_recurrence(lease)
    row.new_annual_cents, row.new_deposit_cents = leases.annual_total(lease), lease.deposit_cents
    row.status, row.applied_at, row.note = "applied", datetime.utcnow(), None
    lease.index_reference_period, lease.index_reference_value = new_period, new_value
    lease.next_revision_date = recurrence.add_months(due, lease.revision_months or 12, due.day)
    db.session.add(row)
    return row


def revise_due(today: date | None = None, fetch: bool = True) -> dict:
    """Révisions arrivées à échéance (avant la préparation des échéances) ; les indices de l'INSEE
    sont relus au plus une fois par jour s'il en manque. `{applied, pending}` (commit)."""
    today = today or date.today()
    due = _due(today)
    if not due:
        return {"applied": 0, "pending": 0}
    if fetch and any(l.index_code in INSEE_SERIES for l in due) and \
            (last_fetch() is None or datetime.utcnow() - last_fetch() > FETCH_EVERY):
        try:
            fetch_insee()
        except RevisionError:
            pass  # INSEE indisponible : les révisions restent en attente
    applied = pending = 0
    for lease in due:
        # Plusieurs révisions en retard (bail repris, application fermée longtemps) : une à une.
        for _ in range(10):
            row = revise(lease)
            if row.status != "applied":
                pending += 1
                break
            applied += 1
            if lease.next_revision_date > today:
                break
    db.session.commit()
    return {"applied": applied, "pending": pending}
