"""Pièces des factures d'achat saisies, rangées dans le dossier de l'instance.

`instance/uploads/<slug>/achats/AAAA/MM/<id>-<nom assaini>` (date de facture). Un
fichier déposé attend d'abord dans `…/<slug>/tmp/<jeton>` le temps de la lecture et
de la vérification du formulaire ; il est déplacé à l'enregistrement de la facture.
Les chemins sont toujours construits ici et vérifiés dans le dossier de l'instance :
rien ne vient du formulaire, sauf un jeton hexadécimal contrôlé.
"""
from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from pathlib import Path

from flask import current_app
from werkzeug.utils import secure_filename

from app.models import Purchase
from app.tenant import current_instance

MAX_SIZE = 10 * 1024 * 1024
STAGING_TTL = 24 * 3600
STAGING_DIR = "tmp"
_TOKEN = re.compile(r"[0-9a-f]{32}")
_SIGNATURES = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
)


class AttachmentError(ValueError):
    pass


def uploads_dir_for(slug: str) -> Path:
    """Dossier des pièces d'une instance (sauvegardes, restauration)."""
    return Path(current_app.instance_path, "uploads", secure_filename(slug or "") or "default")


def instance_dir() -> Path:
    """Dossier des pièces de l'instance courante (« default » hors requête d'instance)."""
    inst = current_instance()
    return uploads_dir_for(inst.slug if inst is not None else "")


def _staging_dir() -> Path:
    return instance_dir() / STAGING_DIR


def _within(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise AttachmentError("Chemin de pièce invalide.")
    return resolved


def sniff(head: bytes) -> tuple[str, str] | None:
    """(type MIME, extension) d'après l'en-tête du fichier."""
    for signature, mime, ext in _SIGNATURES:
        if head.startswith(signature):
            return mime, ext
    return None


def safe_name(name: str, ext: str) -> str:
    stem = secure_filename(Path(name or "").stem)[:80] or "facture"
    return stem + ext


def stage(file_storage) -> str:
    """Met en attente un fichier déposé (PDF, JPEG, PNG ≤ 10 Mo) ; renvoie son jeton."""
    if file_storage is None or not file_storage.filename:
        raise AttachmentError("Aucun fichier.")
    body = file_storage.stream.read(MAX_SIZE + 1)
    if len(body) > MAX_SIZE:
        raise AttachmentError(f"Fichier trop volumineux (maximum {MAX_SIZE // (1024 * 1024)} Mo).")
    if not body:
        raise AttachmentError("Fichier vide.")
    kind = sniff(body[:16])
    if kind is None:
        raise AttachmentError("Type de fichier non accepté : PDF, JPEG ou PNG.")
    purge_staging()
    token = secrets.token_hex(16)
    folder = _staging_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / token).write_bytes(body)
    meta = {"name": Path(file_storage.filename).name[:200], "mime": kind[0], "ext": kind[1],
            "size": len(body)}
    (folder / f"{token}.json").write_text(json.dumps(meta), encoding="utf-8")
    return token


def staged(token: str) -> tuple[Path, dict]:
    """(chemin, métadonnées) d'un fichier en attente ; AttachmentError si le jeton est inconnu."""
    if not _TOKEN.fullmatch(token or ""):
        raise AttachmentError("Pièce en attente introuvable.")
    folder = _staging_dir()
    path, meta_path = folder / token, folder / f"{token}.json"
    if not path.is_file() or not meta_path.is_file():
        raise AttachmentError("Pièce en attente introuvable : déposez à nouveau le fichier.")
    return _within(path, folder), json.loads(meta_path.read_text(encoding="utf-8"))


def store(purchase: Purchase, token: str) -> None:
    """Range la pièce en attente avec la facture (qui doit avoir un id) ; sans commit."""
    source, meta = staged(token)
    day = purchase.issue_date
    sub = Path("achats", f"{day.year:04d}", f"{day.month:02d}") if day else Path("achats", "sans-date")
    relative = sub / f"{purchase.id}-{safe_name(meta['name'], meta['ext'])}"
    target = _within(instance_dir() / relative, instance_dir())
    target.parent.mkdir(parents=True, exist_ok=True)
    old = path_of(purchase)
    shutil.move(source, target)
    (_staging_dir() / f"{token}.json").unlink(missing_ok=True)
    if old is not None and old != target:
        old.unlink(missing_ok=True)
    purchase.attachment_path = relative.as_posix()
    purchase.attachment_name = meta["name"]
    purchase.attachment_mime = meta["mime"]
    purchase.attachment_size = meta["size"]


def path_of(purchase: Purchase) -> Path | None:
    """Fichier de la pièce, vérifié dans le dossier de l'instance ; None s'il n'y en a pas."""
    if not purchase.attachment_path:
        return None
    try:
        path = _within(instance_dir() / purchase.attachment_path, instance_dir())
    except AttachmentError:
        return None
    return path if path.is_file() else None


def purge_staging(max_age: int = STAGING_TTL) -> int:
    """Supprime les fichiers en attente depuis plus de `max_age` secondes."""
    folder = _staging_dir()
    if not folder.is_dir():
        return 0
    limit = time.time() - max_age
    removed = 0
    for path in folder.iterdir():
        if path.is_file() and path.stat().st_mtime < limit:
            path.unlink(missing_ok=True)
            removed += 1
    return removed
