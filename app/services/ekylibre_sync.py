"""Connecteur Ekylibre, lot AG11.a : connexion (jeton obtenu une fois, mot de passe non conservé), révocation,
synchronisation en tâche de fond vers un instantané local (`ekylibre_snapshots`).

La synchronisation lit les cultures, les interventions et les matières par l'adaptateur (`ekylibre_client`) et
remplace l'instantané de chaque type en une transaction. Les sous-lots AG11.b à AG11.d travaillent sur l'instantané.
"""
from __future__ import annotations

import dataclasses
from datetime import date, datetime
from decimal import Decimal

from app.extensions import db
from app.models import EkylibreSnapshot
from app.services import ekylibre_client, external_config
from app.services.ekylibre_client import EkylibreError, Intervention, Matter, Production

KINDS = {"productions": Production, "interventions": Intervention, "matters": Matter}
LABELS = {"productions": "cultures", "interventions": "interventions", "matters": "matières"}


# ------------------------------------------------------------------ connexion

def connect(url: str, email: str, password: str) -> None:
    """Obtient le jeton et enregistre l'adresse, l'email et le jeton (sans commit du test)."""
    base = ekylibre_client.check_url(url)
    token = ekylibre_client.obtain_token(base, email, password)
    external_config.set_many("ekylibre", {"url": base, "email": email.strip(), "token": token})


def revoke() -> None:
    """Révoque le jeton chez Ekylibre (si possible) et l'efface de Lyvre dans tous les cas."""
    url, token = external_config.get("ekylibre", "url"), external_config.get("ekylibre", "token")
    error = None
    if url and token:
        try:
            ekylibre_client.revoke_token(url, token)
        except EkylibreError as exc:
            error = exc
    external_config.set_many("ekylibre", {"url": url or "", "email": external_config.get("ekylibre", "email") or "",
                                          "token": ""})
    if error is not None and error.status != 404:
        raise EkylibreError(f"Jeton effacé de Lyvre, mais Ekylibre n'a pas confirmé sa révocation : {error.message}")


# ------------------------------------------------------------------ instantané

def _plain(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _load(cls, row: dict):
    out = {}
    for f in dataclasses.fields(cls):
        value = row.get(f.name)
        if value is None:
            out[f.name] = f.default_factory() if f.default_factory is not dataclasses.MISSING else None
            continue
        kind = str(f.type)
        if "Decimal" in kind and "dict" not in kind:
            value = Decimal(value)
        elif "dict[str, Decimal]" in kind:
            value = {k: Decimal(v) for k, v in value.items()}
        elif "datetime" in kind:
            value = datetime.fromisoformat(value)
        elif "date" in kind:
            value = date.fromisoformat(value)
        out[f.name] = value
    return cls(**out)


def save_snapshot(kind: str, items: list) -> EkylibreSnapshot:
    row = EkylibreSnapshot.query.filter_by(kind=kind).first() or EkylibreSnapshot(kind=kind)
    row.payload = [_plain(dataclasses.asdict(item)) for item in items]
    row.count, row.synced_at = len(items), datetime.utcnow()
    db.session.add(row)
    return row


def snapshot(kind: str) -> tuple[list, datetime | None]:
    """(objets neutres, date de synchronisation) de l'instantané ; ([], None) s'il n'y en a pas."""
    row = EkylibreSnapshot.query.filter_by(kind=kind).first()
    if row is None:
        return [], None
    return [_load(KINDS[kind], item) for item in row.payload], row.synced_at


def status() -> dict:
    rows = {r.kind: r for r in EkylibreSnapshot.query.all()}
    return {kind: {"label": LABELS[kind], "count": rows[kind].count if kind in rows else None,
                   "synced_at": rows[kind].synced_at.isoformat() if kind in rows else None} for kind in KINDS}


def sync(client=None, progress_cb=None) -> dict:
    client = client or ekylibre_client.Client.from_config()
    fetched = {}
    for index, (kind, method) in enumerate((("productions", client.productions), ("interventions", client.interventions),
                                            ("matters", client.matters))):
        fetched[kind] = method()
        if progress_cb:
            progress_cb(index + 1, len(KINDS))
    for kind, items in fetched.items():  # tout ou rien : aucun instantané partiel
        save_snapshot(kind, items)
    db.session.commit()
    return {"imported": sum(len(v) for v in fetched.values()), "counts": {k: len(v) for k, v in fetched.items()},
            "errors": []}


def start_sync(app):
    from app.models.sync_job import SYNC_KIND_EKYLIBRE
    from app.services import integrations, sync_jobs

    def work(job_id):
        return sync(progress_cb=sync_jobs.progress_callback(job_id))

    def error_message(exc):
        return integrations.mask_secrets("ekylibre", integrations.describe_error("ekylibre", exc))

    return sync_jobs.start(app, SYNC_KIND_EKYLIBRE, work, message="Lecture d'Ekylibre…", error_message=error_message)


def latest_job():
    from app.models import SyncJob
    from app.models.sync_job import SYNC_KIND_EKYLIBRE
    return SyncJob.query.filter_by(kind=SYNC_KIND_EKYLIBRE).order_by(SyncJob.started_at.desc(), SyncJob.id.desc()).first()
