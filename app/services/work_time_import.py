"""Import en masse des temps de travaux (CSV ou XLSX).

Colonnes attendues (insensibles à la casse) :
- ``Bénévole``      : nom OU email du tiers (résolution email prioritaire si « @ »)
- ``Type de tâche`` : doit correspondre à un ``TaskType.name`` existant
- ``Date``          : ``%d/%m/%Y`` ou ``%Y-%m-%d``
- ``Heures``        : décimale virgule ou point (ex. ``2,5`` ou ``2.5``)
- ``Notes``         : libre (optionnel)

Politique doublons : import **additif** (pas de déduplication) — un bénévole
peut effectuer plusieurs sessions le même jour.

Retour : ``{"imported": n, "errors": [...], "skipped": n}``.
"""
import csv
import io
from datetime import datetime

from app.extensions import db
from app.models import Entity, TaskType, WorkTime
from app.services.entity_resolver import entity_by_email


# En-têtes acceptés (normalisés en minuscules, sans accents superflus).
COL_BENEVOLE = ("bénévole", "benevole")
COL_TASK_TYPE = ("type de tâche", "type de tache", "type")
COL_DATE = ("date",)
COL_HOURS = ("heures", "hours")
COL_NOTES = ("notes", "note")

DATE_FORMATS = ("%d/%m/%Y", "%Y-%m-%d")


def _norm(s):
    return (s or "").strip().lower()


def _pick(row, keys):
    """Retourne la valeur de la première colonne dont l'en-tête (normalisé) matche."""
    for header, value in row.items():
        if _norm(header) in keys:
            return value
    return None


def _parse_date(raw):
    value = (raw or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_hours(raw):
    value = (raw or "").strip().replace(",", ".")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _read_rows(file_stream, filename):
    """Retourne une liste de dicts {header: value} depuis un CSV ou XLSX."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xls")):
        import pandas as pd
        df = pd.read_excel(file_stream, dtype=str).fillna("")
        return [
            {str(k): ("" if v is None else str(v)) for k, v in rec.items()}
            for rec in df.to_dict(orient="records")
        ]
    # CSV : même convention que l'export (délimiteur « ; », BOM utf-8-sig).
    raw = file_stream.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8-sig")
    else:
        text = raw
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    return list(reader)


def _resolve_entity(raw, cache):
    """Résout un bénévole par email (si « @ ») sinon par nom (insensible à la casse)."""
    value = (raw or "").strip()
    if not value:
        return None
    if "@" in value:
        return entity_by_email(cache, value)
    return Entity.query.filter(db.func.lower(Entity.name) == value.lower()).first()


def import_work_times(file_stream, filename):
    rows = _read_rows(file_stream, filename)

    imported = 0
    skipped = 0
    errors = []
    email_cache = {}
    # Cache des types de tâches par nom normalisé.
    type_by_name = {
        _norm(tt.name): tt for tt in TaskType.query.all()
    }

    for i, row in enumerate(rows, start=2):  # ligne 1 = en-têtes
        benevole_raw = _pick(row, COL_BENEVOLE)
        type_raw = _pick(row, COL_TASK_TYPE)
        date_raw = _pick(row, COL_DATE)
        hours_raw = _pick(row, COL_HOURS)
        notes_raw = _pick(row, COL_NOTES)

        # Ligne entièrement vide → ignorée silencieusement.
        if not any([_norm(benevole_raw), _norm(type_raw), _norm(date_raw),
                    _norm(hours_raw)]):
            skipped += 1
            continue

        entity = _resolve_entity(benevole_raw, email_cache)
        if entity is None:
            errors.append(f"Ligne {i} : bénévole introuvable « {(benevole_raw or '').strip()} ».")
            continue

        task_type = type_by_name.get(_norm(type_raw))
        if task_type is None:
            errors.append(f"Ligne {i} : type de tâche inconnu « {(type_raw or '').strip()} ».")
            continue

        work_date = _parse_date(date_raw)
        if work_date is None:
            errors.append(f"Ligne {i} : date invalide « {(date_raw or '').strip()} ».")
            continue

        hours = _parse_hours(hours_raw)
        if hours is None or hours <= 0:
            errors.append(f"Ligne {i} : nombre d'heures invalide « {(hours_raw or '').strip()} ».")
            continue

        db.session.add(WorkTime(
            entity_id=entity.id,
            task_type_id=task_type.id,
            work_date=work_date,
            hours=hours,
            notes=(notes_raw or "").strip() or None,
        ))
        imported += 1

    db.session.commit()
    return {"imported": imported, "errors": errors, "skipped": skipped}
