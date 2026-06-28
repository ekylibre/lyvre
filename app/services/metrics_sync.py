"""Écriture des métriques stockées : upsert idempotent + orchestration de synchro.

- `upsert_snapshot` : insertion/maj sur la clé unique (saisie manuelle + API).
- `sync_metrics` : récupère les sources externes (GA4, Facebook) et journalise via
  `SyncJob`. Tolérant aux pannes : une source en échec n'interrompt pas les autres.
"""
from datetime import datetime

from app.extensions import db
from app.models import MetricSnapshot, SyncJob
from app.models.sync_job import (
    SYNC_KIND_METRICS, SYNC_STATUS_DONE, SYNC_STATUS_FAILED,
)


def upsert_snapshot(source, metric_key, period_start, value, unit,
                    granularity="month", is_manual=False, user_id=None, note=None):
    """Insère ou met à jour la métrique (clé unique source/key/period/granularité).

    N'effectue PAS de commit : le caller regroupe et commite.
    """
    row = (
        db.session.query(MetricSnapshot)
        .filter_by(source=source, metric_key=metric_key,
                   period_start=period_start, granularity=granularity)
        .first()
    )
    if row is None:
        row = MetricSnapshot(
            source=source, metric_key=metric_key, period_start=period_start,
            granularity=granularity,
        )
        db.session.add(row)
    row.value = value
    row.unit = unit
    row.is_manual = is_manual
    row.entered_by_user_id = user_id
    row.note = note
    row.captured_at = datetime.utcnow()
    return row


def _period_start_for(year, month):
    from datetime import date
    return date(year, month, 1)


def sync_metrics(year, month):
    """Synchronise GA4 + Facebook pour le mois donné. Retourne un récap par source."""
    period_start = _period_start_for(year, month)
    result = {}
    job = SyncJob(kind=SYNC_KIND_METRICS, status="running")
    db.session.add(job)
    db.session.commit()

    try:
        result["ga4"] = _sync_ga4(year, month, period_start)
        result["facebook"] = _sync_facebook(period_start)
        job.status = SYNC_STATUS_DONE
    except Exception as exc:  # garde-fou : ne devrait pas arriver (sous-fonctions tolérantes)
        job.status = SYNC_STATUS_FAILED
        job.message = str(exc)
    finally:
        import json
        job.finished_at = datetime.utcnow()
        try:
            job.result_json = json.dumps(result, default=str)
        except (TypeError, ValueError):
            job.result_json = None
        db.session.commit()
    return result


def _sync_ga4(year, month, period_start):
    """Récupère les métriques GA4 du mois (tolérant aux erreurs/non-configuré)."""
    info = {"imported": 0, "errors": []}
    try:
        from app.services.ga4_client import from_app_config, GA4ConfigError
    except Exception as exc:
        info["errors"].append(f"GA4 indisponible : {exc}")
        return info
    try:
        client = from_app_config()
    except GA4ConfigError as exc:
        info["errors"].append(str(exc))
        return info
    try:
        metrics = client.fetch_monthly(year, month)  # {metric_key: value}
    except Exception as exc:
        info["errors"].append(f"GA4 : {exc}")
        return info

    from app.services import metric_catalog
    for key, value in metrics.items():
        m = metric_catalog.get(key)
        unit = m.unit if m else "count"
        upsert_snapshot("ga4", key, period_start, value, unit)
        info["imported"] += 1
    db.session.commit()
    return info


def _sync_facebook(period_start):
    info = {"imported": 0, "errors": []}
    try:
        from app.services.facebook_client import from_app_config, FacebookConfigError
    except Exception as exc:
        info["errors"].append(f"Facebook indisponible : {exc}")
        return info
    try:
        client = from_app_config()
    except FacebookConfigError as exc:
        info["errors"].append(str(exc))
        return info
    try:
        followers = client.fetch_page_followers()
    except Exception as exc:
        info["errors"].append(f"Facebook : {exc}")
        return info

    upsert_snapshot("facebook_page", "facebook_page.followers", period_start,
                    followers, "count")
    info["imported"] += 1
    db.session.commit()
    return info
