"""Export iCal de l'échéancier (lot AG9a.e, claudedocs/design_echeancier_agricole.md § 8, Q-E3).

- Une URL secrète par utilisateur et par instance : `/agenda/ical/<instance>/<jeton>.ics`, le jeton (aléatoire,
  256 bits) dans `agenda_subscriptions.ical_token` ; il se régénère (l'ancienne URL cesse de marcher) ou se révoque.
- L'URL vaut tant que l'utilisateur est actif et a un rôle sur l'instance : un accès retiré coupe le calendrier.
- Occurrences de J-30 à J+400, un événement « journée entière » chacune, avec le lien vers Lyvre ; lecture seule
  (les paiements ne sont pas rattachés à la lecture du calendrier).
- Format RFC 5545 : lignes terminées par CRLF, pliées à 75 octets, texte échappé ; UID stable par occurrence pour
  que le logiciel d'agenda mette à jour l'événement au lieu de le dupliquer.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta, timezone

from app.extensions import db
from app.models import AgendaSubscription

PAST_DAYS, FUTURE_DAYS = 30, 400
PRODID = "-//Lyvre//Echeancier//FR"


# ------------------------------------------------------------------ jeton

def token_of(user_id: int) -> str | None:
    row = AgendaSubscription.query.filter_by(user_id=user_id).first()
    return row.ical_token if row else None


def regenerate(user_id: int) -> str:
    """Nouveau jeton (sans commit) : l'ancienne URL cesse de marcher."""
    row = AgendaSubscription.query.filter_by(user_id=user_id).first()
    if row is None:
        row = AgendaSubscription(user_id=user_id)
        db.session.add(row)
    row.ical_token = secrets.token_urlsafe(32)
    db.session.flush()
    return row.ical_token


def revoke(user_id: int) -> None:
    row = AgendaSubscription.query.filter_by(user_id=user_id).first()
    if row is not None:
        row.ical_token = None
        db.session.flush()


def owner_of(token: str) -> int | None:
    """Utilisateur du jeton, ou None (comparaison à temps constant)."""
    if not token or len(token) < 20:
        return None
    row = AgendaSubscription.query.filter_by(ical_token=token).first()
    if row is None or not secrets.compare_digest(row.ical_token, token):
        return None
    return row.user_id


# ------------------------------------------------------------------ format

def escape(text: str) -> str:
    """Texte RFC 5545 § 3.3.11 : antislash, point-virgule, virgule, sauts de ligne."""
    return (str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n"))


def fold(line: str) -> str:
    """Pliage RFC 5545 § 3.1 : 75 octets au plus par ligne, sans couper un caractère UTF-8 ; la suite commence
    par une espace."""
    out, current, size = [], "", 0
    for char in line:
        width = len(char.encode("utf-8"))
        limit = 75 if not out else 74          # la ligne de suite commence par une espace
        if size + width > limit:
            out.append(current)
            current, size = "", 0
        current += char
        size += width
    out.append(current)
    return "\r\n ".join(out)


def _euros(cents: int) -> str:
    return f"{cents / 100:,.2f}".replace(",", " ").replace(".", ",") + " €"


def _uid(key: str, instance_slug: str) -> str:
    return hashlib.sha256(f"{instance_slug}|{key}".encode()).hexdigest()[:32] + "@lyvre"


def _event(item: dict, statuses: dict, base_url: str, slug: str, stamp: str) -> list[str]:
    day = item["date"]
    summary = f"{item['label']} — {item['period']}"
    if item["status"] in ("done", "skipped"):
        summary = f"[{statuses[item['status']]}] {summary}"
    elif item["to_confirm"]:
        summary += " (date à confirmer)"
    link = f"{base_url}{item.get('link') or (item.get('action') or {}).get('route') or '/agenda/'}"
    details = [f"{item['title']} — {item['organism']}", f"Statut : {statuses.get(item['status'], item['status'])}"]
    if item["amount_cents"]:
        details.append(f"Montant {'calculé par Lyvre' if item['amount_proposed'] else 'enregistré'} : "
                       f"{_euros(item['amount_cents'])}")
    if item.get("edi_date"):
        details.append(f"Télédéclaration jusqu'au {item['edi_date']:%d/%m/%Y}")
    if item["to_confirm"]:
        details.append("Date à confirmer.")
    details.append(link)
    lines = ["BEGIN:VEVENT", f"UID:{_uid(item['key'], slug)}", f"DTSTAMP:{stamp}",
             f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
             f"SUMMARY:{escape(summary)}", f"DESCRIPTION:{escape(chr(10).join(details))}", f"URL:{link}",
             f"CATEGORIES:{escape(item['domain'].upper())}", "TRANSP:TRANSPARENT",
             f"STATUS:{'TENTATIVE' if item['to_confirm'] else 'CONFIRMED'}"]
    if item["status"] not in ("done", "skipped"):
        lead = (day - item["reminder_from"]).days
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{escape(item['label'])}",
                  f"TRIGGER:-P{lead}D", "END:VALARM"]
    lines.append("END:VEVENT")
    return lines


def calendar(name: str, slug: str, base_url: str, today: date | None = None, now: datetime | None = None) -> str:
    """Calendrier de l'instance courante, de J-30 à J+400."""
    from app.services import agenda

    today = today or date.today()
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    items = agenda.occurrences(today - timedelta(days=PAST_DAYS), today + timedelta(days=FUTURE_DAYS), today)["items"]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
             f"X-WR-CALNAME:{escape(f'Échéancier — {name}')}", "X-WR-TIMEZONE:Europe/Paris",
             "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H"]
    for item in items:
        lines += _event(item, agenda.STATUSES, base_url, slug, stamp)
    lines.append("END:VCALENDAR")
    return "".join(fold(line) + "\r\n" for line in lines)
