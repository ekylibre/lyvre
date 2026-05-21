"""SQLite backup and restore for tenant instances.

Backups are atomic copies created via SQLite's online backup API
(`sqlite3.Connection.backup`). Files land in `<instance_folder>/backups/`
and are named `<slug>-YYYYMMDD-HHMMSS.db`.

Postgres instances are out of scope: any call on a non-SQLite database_url
raises BackupError.
"""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from flask import current_app

from app.tenant import clear_engine_cache


SQLITE_MAGIC = b"SQLite format 3\x00"
PRE_RESTORE_PREFIX = "pre-restore-"
MAX_BACKUP_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


class BackupError(RuntimeError):
    pass


@dataclass
class BackupFile:
    filename: str
    path: Path
    size_bytes: int
    created_at: datetime
    is_pre_restore: bool


def _backups_dir() -> Path:
    path = Path(current_app.instance_path) / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _resolve_sqlite_path(database_url: str) -> Path:
    """Return absolute filesystem path for a SQLite URL, or raise BackupError."""
    if not database_url.startswith("sqlite:///"):
        raise BackupError(
            "Sauvegardes disponibles uniquement pour les instances SQLite "
            "(URL actuelle : non-SQLite). Utilisez pg_dump pour Postgres."
        )
    raw = database_url[len("sqlite:///"):]
    path = Path(raw)
    if not path.is_absolute():
        path = Path(current_app.instance_path) / raw
    return path


def _filename_re(slug: str) -> re.Pattern:
    # <slug>-YYYYMMDD-HHMMSS.db, optionally prefixed by 'pre-restore-'
    return re.compile(
        rf"^({re.escape(PRE_RESTORE_PREFIX)})?{re.escape(slug)}-\d{{8}}-\d{{6}}\.db$"
    )


def _safe_backup_path(instance, filename: str) -> Path:
    if not _filename_re(instance.slug).match(filename):
        raise BackupError("Nom de fichier de sauvegarde invalide.")
    path = _backups_dir() / filename
    # Resolve and confirm the path stays inside backups dir (defense in depth).
    if not str(path.resolve()).startswith(str(_backups_dir().resolve())):
        raise BackupError("Chemin de sauvegarde hors du dossier autorisé.")
    return path


def list_backups(instance) -> list[BackupFile]:
    """Return all backups for this instance, newest first."""
    pattern = _filename_re(instance.slug)
    out: list[BackupFile] = []
    backups_dir = _backups_dir()
    for entry in backups_dir.iterdir():
        if not entry.is_file():
            continue
        if not pattern.match(entry.name):
            continue
        stat = entry.stat()
        out.append(BackupFile(
            filename=entry.name,
            path=entry,
            size_bytes=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_mtime),
            is_pre_restore=entry.name.startswith(PRE_RESTORE_PREFIX),
        ))
    out.sort(key=lambda b: b.created_at, reverse=True)
    return out


def create_backup(instance, prefix: str = "") -> Path:
    """Create an atomic backup of the instance's SQLite database."""
    src_path = _resolve_sqlite_path(instance.database_url)
    if not src_path.exists():
        raise BackupError(f"Base introuvable : {src_path}")

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    name = f"{prefix}{instance.slug}-{timestamp}.db"
    target = _backups_dir() / name

    src = sqlite3.connect(str(src_path))
    try:
        dst = sqlite3.connect(str(target))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    return target


def delete_backup(instance, filename: str) -> None:
    path = _safe_backup_path(instance, filename)
    if not path.exists():
        raise BackupError("Sauvegarde introuvable.")
    path.unlink()


def backup_path(instance, filename: str) -> Path:
    path = _safe_backup_path(instance, filename)
    if not path.exists():
        raise BackupError("Sauvegarde introuvable.")
    return path


def _validate_uploaded_sqlite(uploaded_file) -> bytes:
    """Read the upload into memory after sanity checks. Returns file bytes."""
    # Werkzeug FileStorage; size already capped by MAX_CONTENT_LENGTH.
    head = uploaded_file.stream.read(16)
    if head != SQLITE_MAGIC:
        raise BackupError(
            "Le fichier n'est pas une base SQLite valide (magic header invalide)."
        )
    body = uploaded_file.stream.read(MAX_BACKUP_UPLOAD_BYTES + 1)
    if len(body) > MAX_BACKUP_UPLOAD_BYTES:
        raise BackupError(
            f"Le fichier dépasse la taille maximale "
            f"({MAX_BACKUP_UPLOAD_BYTES // (1024 * 1024)} Mo)."
        )
    return head + body


def _stage_and_validate(blob: bytes, target_path: Path) -> Path:
    """Write blob next to target_path, integrity-check, return temp path.

    Caller is responsible for the final os.replace(tmp, target). On failure
    the temp file is removed and BackupError is raised.
    """
    target_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target_path.with_suffix(target_path.suffix + ".incoming")
    tmp_path.write_bytes(blob)
    try:
        conn = sqlite3.connect(str(tmp_path))
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise BackupError(
                    f"PRAGMA integrity_check a échoué : {result[0] if result else 'aucun résultat'}"
                )
        finally:
            conn.close()
    except sqlite3.DatabaseError as e:
        tmp_path.unlink(missing_ok=True)
        raise BackupError(f"Fichier SQLite invalide : {e}") from e
    except BackupError:
        tmp_path.unlink(missing_ok=True)
        raise
    return tmp_path


def restore_from_upload(instance, uploaded_file) -> tuple[Path, Path]:
    """Replace the instance DB with the uploaded SQLite file.

    Returns (pre_restore_backup_path, restored_target_path).
    """
    target_path = _resolve_sqlite_path(instance.database_url)
    blob = _validate_uploaded_sqlite(uploaded_file)
    tmp_path = _stage_and_validate(blob, target_path)

    # Safety: snapshot the current DB before overwriting.
    pre_backup = create_backup(instance, prefix=PRE_RESTORE_PREFIX)

    # Atomic replace (same filesystem).
    os.replace(tmp_path, target_path)

    # Drop cached engine so the next request opens the new file.
    clear_engine_cache(instance.id)

    return pre_backup, target_path


_TIMESTAMPED_RE = re.compile(
    r"^(?P<slug>[a-z0-9][a-z0-9-]*[a-z0-9])-\d{8}-\d{6}\.(?:db|sqlite|backup)$",
    re.IGNORECASE,
)
_PLAIN_RE = re.compile(
    r"^(?P<slug>[a-z0-9][a-z0-9-]*[a-z0-9])\.(?:db|sqlite|backup)$",
    re.IGNORECASE,
)


def extract_slug_from_filename(filename: str) -> str | None:
    """Best-effort slug extraction from an uploaded filename.

    - 'seconde-nature.db'                       → 'seconde-nature'
    - 'seconde-nature-20260521-175502.db'       → 'seconde-nature'
    - 'pre-restore-seconde-nature-20260521-…' → 'seconde-nature'
    - 'export.backup'                           → 'export'
    - 'archive.zip'                             → None
    """
    if not filename:
        return None
    stem = Path(filename).name
    if stem.lower().startswith("pre-restore-"):
        stem = stem[len("pre-restore-"):]
    match = _TIMESTAMPED_RE.match(stem) or _PLAIN_RE.match(stem)
    if not match:
        return None
    return match.group("slug").lower()


def stage_upload_to_path(uploaded_file, target_path: Path) -> None:
    """Validate the upload and atomically write it to target_path.

    Used for NEW instance creation from upload (no pre-restore backup).
    """
    blob = _validate_uploaded_sqlite(uploaded_file)
    tmp_path = _stage_and_validate(blob, target_path)
    os.replace(tmp_path, target_path)


def is_sqlite_instance(instance) -> bool:
    return instance.database_url.startswith("sqlite:///")


def total_size_bytes(instance) -> int:
    return sum(b.size_bytes for b in list_backups(instance))
