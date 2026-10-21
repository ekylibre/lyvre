"""Pièces des factures saisies : mise en attente, rangement, confinement au dossier de l'instance."""
import io
import os
import time
from datetime import date

import pytest
from werkzeug.datastructures import FileStorage

from app.extensions import db
from app.models import Purchase
from app.services import attachments
from app.services.attachments import AttachmentError

PDF = b"%PDF-1.4\n%fake\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 20


@pytest.fixture()
def uploads(app, tmp_path, monkeypatch):
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    return tmp_path


def upload(body, name="Facture EDF.pdf"):
    return FileStorage(stream=io.BytesIO(body), filename=name)


def test_stage_and_read_back(uploads):
    token = attachments.stage(upload(PDF))
    path, meta = attachments.staged(token)
    assert path.read_bytes() == PDF and path.parent == uploads / "uploads" / "default" / "tmp"
    assert meta == {"name": "Facture EDF.pdf", "mime": "application/pdf", "ext": ".pdf", "size": len(PDF)}
    _, meta = attachments.staged(attachments.stage(upload(PNG, "scan.png")))
    assert meta["mime"] == "image/png"


@pytest.mark.parametrize("body, message", [
    (b"MZ\x90\x00 exe", "Type de fichier"),
    (b"", "vide"),
])
def test_stage_rejects(uploads, body, message):
    with pytest.raises(AttachmentError, match=message):
        attachments.stage(upload(body, "facture.pdf"))


def test_stage_size_limit(uploads, monkeypatch):
    monkeypatch.setattr(attachments, "MAX_SIZE", 10)
    with pytest.raises(AttachmentError, match="trop volumineux"):
        attachments.stage(upload(PDF))


@pytest.mark.parametrize("token", ["../../etc/passwd", "ABC", "0" * 31, ""])
def test_bad_tokens(uploads, token):
    with pytest.raises(AttachmentError):
        attachments.staged(token)


def test_store_moves_file_with_purchase(uploads, session):
    p = Purchase(source="manual", issue_date=date(2026, 9, 29), total_cents=100)
    db.session.add(p)
    db.session.flush()
    token = attachments.stage(upload(PDF, "../../Ticket de caisse.pdf"))
    attachments.store(p, token)
    assert p.attachment_path == f"achats/2026/09/{p.id}-Ticket_de_caisse.pdf"
    assert p.attachment_name == "Ticket de caisse.pdf" and p.attachment_size == len(PDF)
    assert attachments.path_of(p).read_bytes() == PDF
    with pytest.raises(AttachmentError):
        attachments.staged(token)  # consommée

    # Remplacement : l'ancienne pièce disparaît.
    old = attachments.path_of(p)
    attachments.store(p, attachments.stage(upload(PNG, "photo.png")))
    assert not old.exists() and attachments.path_of(p).suffix == ".png"


def test_path_outside_instance_refused(uploads, session):
    secret = uploads / "secret.txt"
    secret.write_text("x")
    p = Purchase(source="manual", total_cents=1, attachment_path="../secret.txt")
    assert attachments.path_of(p) is None


def test_purge_staging(uploads):
    token = attachments.stage(upload(PDF))
    path, _ = attachments.staged(token)
    old = time.time() - 2 * attachments.STAGING_TTL
    for f in path.parent.iterdir():
        os.utime(f, (old, old))
    assert attachments.purge_staging() == 2
    with pytest.raises(AttachmentError):
        attachments.staged(token)
