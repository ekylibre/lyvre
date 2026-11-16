"""Journal des appels par clé d'API et limites (lot AK4, claudedocs/design_api_mcp_aiffel.md § 3.2, § 8).

- Journal (`api_calls`, base de l'instance) : chaque appel REST et chaque outil MCP, accepté ou refusé ; jamais la clé
  ni le contenu de la requête. Purge des lignes de plus de 180 jours, une fois par jour.
- Débit : fenêtre glissante d'une minute en mémoire, par clé (un seul processus gunicorn, D7).
- Plafond quotidien de créations : compté dans le journal (jour de Paris), il survit à un redémarrage.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.extensions import db

RETENTION_DAYS = 180
WINDOW_SECONDS = 60
PARIS = ZoneInfo("Europe/Paris")
JOURNAL_LIMIT = 200

_hits: dict[int, deque] = defaultdict(deque)
_lock = threading.Lock()
_purged_on: dict[int, str] = {}       # instance → dernier jour de purge
_last_used: dict[int, float] = {}     # clé → dernière écriture de last_used_at (horloge monotone)


# ------------------------------------------------------------------ débit


def rate_check(key_id: int, per_minute: int, now: float | None = None) -> int | None:
    """None si l'appel passe (il est compté), sinon le délai d'attente en secondes."""
    now = time.monotonic() if now is None else now
    with _lock:
        hits = _hits[key_id]
        while hits and hits[0] <= now - WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= per_minute:
            return max(1, int(hits[0] + WINDOW_SECONDS - now) + 1)
        hits.append(now)
    return None


def reset() -> None:
    """Compteurs en mémoire remis à zéro (tests : les identifiants de clé et d'instance repartent de 1)."""
    with _lock:
        _hits.clear()
    _purged_on.clear()
    _last_used.clear()


def _day_start_utc(now: datetime | None = None) -> datetime:
    """Début du jour de Paris, en UTC naïf (comme `api_calls.at`)."""
    local = (now or datetime.now(timezone.utc)).astimezone(PARIS)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).replace(tzinfo=None)


def creations_today(key_id: int) -> int:
    from app.models import ApiCall
    return ApiCall.query.filter(ApiCall.key_id == key_id, ApiCall.object_id.isnot(None),
                                ApiCall.at >= _day_start_utc()).count()


# ------------------------------------------------------------------ journal


def record(key_id: int, channel: str, target: str, *, domain=None, access=None, status=200, error=None,
           object_type=None, object_id=None, idempotency_key=None, duration_ms=None) -> None:
    """Inscrit un appel (commit). Ne lève jamais : le journal ne doit pas faire échouer l'appel."""
    from flask import current_app
    from app.models import ApiCall
    try:
        db.session.add(ApiCall(key_id=key_id, channel=channel, target=target[:80], domain=domain, access=access,
                               status=status, error=(error or "")[:300] or None, object_type=object_type,
                               object_id=object_id, idempotency_key=idempotency_key, duration_ms=duration_ms))
        db.session.commit()
        _purge_once_a_day()
    except Exception:  # noqa: BLE001
        db.session.rollback()
        current_app.logger.exception("Journal des clés d'API : appel non inscrit")


def _purge_once_a_day() -> None:
    from app.models import ApiCall
    from app.tenant import current_instance
    inst = current_instance()
    today = datetime.now(PARIS).date().isoformat()
    if inst is None or _purged_on.get(inst.id) == today:
        return
    _purged_on[inst.id] = today
    ApiCall.query.filter(ApiCall.at < datetime.utcnow() - timedelta(days=RETENTION_DAYS)).delete()
    db.session.commit()


def touch(key_id: int) -> None:
    """`last_used_at` de la clé (méta-base), au plus une fois par minute."""
    from app.models import ApiKey
    now = time.monotonic()
    if now - _last_used.get(key_id, -WINDOW_SECONDS) < WINDOW_SECONDS:
        return
    _last_used[key_id] = now
    db.session.query(ApiKey).filter_by(id=key_id).update({"last_used_at": datetime.utcnow()})
    db.session.commit()


def entries(key_id: int, kind: str | None = None, limit: int = JOURNAL_LIMIT) -> list[dict]:
    from app.models import ApiCall
    from app.services import api_domains
    query = ApiCall.query.filter_by(key_id=key_id)
    if kind == "errors":
        query = query.filter(ApiCall.status >= 400)
    elif kind == "creations":
        query = query.filter(ApiCall.object_id.isnot(None))
    rows = query.order_by(ApiCall.at.desc(), ApiCall.id.desc()).limit(limit).all()
    return [{"id": c.id, "at": c.at.isoformat(), "channel": c.channel, "target": c.target, "domain": c.domain,
             "domain_label": api_domains.label(c.domain) if c.domain else None, "access": c.access,
             "status": c.status, "error": c.error, "object": _object_link(c), "duration_ms": c.duration_ms}
            for c in rows]


_OBJECT_PATHS = {"purchase": ("/purchases/{}", "Facture d'achat"), "entity": ("/entities/{}", "Tiers"),
                 "journal_entry": ("/entries/{}", "Écriture")}


def _object_link(call) -> dict | None:
    if not call.object_type or not call.object_id or call.object_type not in _OBJECT_PATHS:
        return None
    path, label = _OBJECT_PATHS[call.object_type]
    return {"type": call.object_type, "id": call.object_id, "url": path.format(call.object_id),
            "label": f"{label} n° {call.object_id}"}
