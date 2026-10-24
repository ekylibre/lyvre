"""Signature électronique des baux (lot L4, BF13–BF17) avec Documenso.

- Signataires : les **gérants** (registre des associés, case « Gérant », e-mail de leur fiche tiers),
  dans l'ordre du registre, puis le **preneur** (e-mail de sa fiche, sinon premier e-mail de
  facturation) ; Documenso les sollicite dans cet ordre.
- Envoi : le PDF du bail est figé (`baux/<bail>/bail-envoye-<n>.pdf`) avec, dans chaque case du bloc de
  signatures, une balise de champ Documenso (`{{signature, r1}}` : r1 = premier signataire) ; l'envoi
  est créé, les champs de signature agrandis, une case de **paraphe** par signataire ajoutée en bas à
  droite de chaque page, puis les invitations partent.
- Suivi : `refresh` lit l'état de l'envoi ; signé, le PDF signé et le journal d'audit sont rangés
  avec le bail. Un bail envoyé (ou signé) n'est plus modifiable dans ses termes ; annuler l'envoi le
  rend modifiable (BF17).
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timedelta

from pypdf import PdfReader

from markupsafe import escape

from app.extensions import db
from app.models import Associate, Lease, LeaseSignature, LeaseSigner
from app.services import documenso, lease_documents
from app.services.attachments import instance_dir
from app.services.lease_map import folder
from app.services.sale_entry import SaleError

STATUS_LABELS = {"sent": "Envoyé à la signature", "completed": "Signé", "declined": "Signature refusée",
                 "expired": "Envoi expiré", "cancelled": "Envoi annulé"}
SIGNER_LABELS = {"awaiting": "En attente", "sent": "Invitation envoyée", "opened": "Ouvert", "completed": "Signé",
                 "declined": "Refusé"}
REFRESH_EVERY = timedelta(minutes=1)
SIGNATURE_SIZE = (32.0, 7.0)  # largeur et hauteur des champs de signature, en % de la page (case de 24 mm)
# Paraphes : une case par signataire en bas à droite de chaque page, côte à côte, la dernière contre la
# marge droite (18 mm), dans la bande entre la fin du texte (marge basse de 22 mm) et le pied de page
# (au ras du bas) : jamais sur le texte ni sur le pied de page, quel que soit le nombre de signataires ;
# en % de la page A4.
INITIALS_WIDTH, INITIALS_HEIGHT, INITIALS_STEP, INITIALS_RIGHT, INITIALS_TOP = 9.0, 2.6, 10.0, 91.4, 93.0


def initials_boxes(count: int) -> list[tuple[float, float, float, float]]:
    return [(round(INITIALS_RIGHT - INITIALS_WIDTH - (count - 1 - n) * INITIALS_STEP, 2), INITIALS_TOP,
             INITIALS_WIDTH, INITIALS_HEIGHT) for n in range(count)]
ENVELOPE_STATUS = {"COMPLETED": "completed", "REJECTED": "declined", "CANCELLED": "cancelled"}
BOX = re.compile(r"""<div class=["']sign-box sign-(\w+)["']></div>""")


def _first_email(*values) -> str:
    for value in values:
        for part in re.split(r"[,;\s]+", value or ""):
            if "@" in part:
                return part.strip()
    return ""


def planned(lease: Lease) -> tuple[list[dict], list[str]]:
    """Signataires prévus (clé, rôle, nom, e-mail) et ce qui empêche l'envoi."""
    signers, problems = [], []
    managers = Associate.query.filter_by(is_manager=True).order_by(Associate.id).all()
    if not managers:
        problems.append("Aucun gérant : cochez « Gérant » sur la fiche des associés qui signent (Associés).")
    for n, manager in enumerate(managers, start=1):
        email = _first_email(manager.entity.email)
        if not email:
            problems.append(f"E-mail manquant sur la fiche tiers du gérant {manager.name}.")
        signers.append({"key": f"l{n}", "role": f"Bailleur {n}", "name": manager.name, "email": email,
                        "associate_id": manager.id, "entity_id": None})
    tenant = lease.entity
    email = _first_email(tenant.email, tenant.billing_emails)
    if not email:
        problems.append(f"E-mail manquant sur la fiche du preneur {tenant.name}.")
    signers.append({"key": "t", "role": "Preneur", "name": tenant.name, "email": email, "associate_id": None,
                    "entity_id": tenant.id})
    return signers, problems


def current(lease: Lease) -> LeaseSignature | None:
    """Dernier envoi non annulé."""
    return next((s for s in reversed(lease.signatures) if s.status != "cancelled"), None)


def with_tags(body: str, signers: list[dict]) -> str:
    """Balises Documenso dans les cases du bloc de signatures (`{{signature, r1}}`, numérotées dans
    l'ordre de signature) ; une page de signatures en plus pour les signataires sans case (texte
    rédigé avant le lot L4, gérants ajoutés depuis)."""
    by_key = {s["key"]: s for s in signers}
    rank = {s["key"]: n for n, s in enumerate(signers, start=1)}

    def tag(signer):
        # Balise sur une seule ligne, lue dans le texte du PDF ; le champ prend la taille du texte.
        return f'<div class="sign-box"><span class="sign-tag">{{{{signature, r{rank[signer["key"]]}}}}}</span></div>'

    placed = set()

    def fill(match):
        signer = by_key.get(match.group(1))
        if signer is None:
            return match.group(0)
        placed.add(signer["key"])
        return tag(signer)

    body = BOX.sub(fill, body)
    missing = [s for s in signers if s["key"] not in placed]
    if missing:
        cells = "".join(f"<td><b>{escape(s['role'])}</b><br>{escape(s['name'])}{tag(s)}</td>" for s in missing)
        body += f'<div class="signature-page"><h2>Signatures</h2><table class="signatures"><tr>{cells}</tr></table></div>'
    return body


def send(lease: Lease, user_id=None, client: documenso.Client | None = None,
         send_email: bool = True) -> LeaseSignature:
    if lease.status != "active":
        raise SaleError("Validez le bail avant de l'envoyer à la signature.", status=409)
    if current(lease) is not None and current(lease).status in ("sent", "completed"):
        raise SaleError("Ce bail est déjà envoyé à la signature.", status=409)
    signers, problems = planned(lease)
    if problems:
        raise SaleError(" ".join(problems), status=409)
    if lease.document_html is None:
        lease_documents.generate(lease)
    pdf = lease_documents.render_pdf(lease, signers=signers)
    client = client or documenso.Client.from_config()
    number = len(lease.signatures) + 1
    path = folder(lease) / f"bail-envoye-{number}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf)
    title = f"Bail {lease.unit_label} — {lease.entity.name}"[:200]
    envelope_id = None
    try:
        envelope_id = client.create_envelope(title, pdf, signers, f"lease-{lease.id}-{number}", send_email=send_email)
        if client.resize_signatures(envelope_id, *SIGNATURE_SIZE) != len(signers):
            raise documenso.DocumensoError("Documenso n'a pas trouvé toutes les cases de signature dans le PDF.")
        client.add_initials(envelope_id, len(PdfReader(io.BytesIO(pdf)).pages), initials_boxes(len(signers)))
        client.distribute(envelope_id)
        remote = client.envelope(envelope_id)
    except documenso.DocumensoError as exc:
        path.unlink(missing_ok=True)
        if envelope_id:  # brouillon créé mais non envoyé : retiré, rien ne reste à moitié fait
            try:
                client.delete(envelope_id)
            except documenso.DocumensoError:
                pass
        raise SaleError(exc.message, status=502) from None
    signature = LeaseSignature(lease=lease, provider="documenso", submission_id=str(envelope_id), status="sent",
                               sent_at=datetime.utcnow(), checked_at=datetime.utcnow(), created_by_id=user_id,
                               sent_pdf_path=str(path.relative_to(instance_dir())))
    for position, s in enumerate(signers):
        signature.signers.append(LeaseSigner(position=position, role=s["role"], name=s["name"], email=s["email"],
                                             associate_id=s["associate_id"], entity_id=s["entity_id"]))
    _apply_recipients(signature, remote)
    db.session.add(signature)
    db.session.commit()
    return signature


def _when(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _recipient_status(r: dict) -> str:
    if r.get("signingStatus") == "SIGNED":
        return "completed"
    if r.get("signingStatus") == "REJECTED":
        return "declined"
    if r.get("readStatus") == "OPENED":
        return "opened"
    if r.get("sendStatus") == "SENT":
        return "sent"
    return "awaiting"


def _apply_recipients(signature: LeaseSignature, remote: dict) -> None:
    """Statut de chaque signataire, apparié par ordre de signature (puis par e-mail)."""
    recipients = sorted(remote.get("recipients") or [], key=lambda r: r.get("signingOrder") or 0)
    for signer in signature.signers:
        r = next((x for x in recipients if x.get("signingOrder") == signer.position + 1), None) or \
            next((x for x in recipients if (x.get("email") or "").lower() == signer.email.lower()), {})
        signer.submitter_id = str(r.get("id") or "") or signer.submitter_id
        signer.status = _recipient_status(r) if r else signer.status
        if signer.status == "completed":
            signer.signed_at = _when(r.get("signedAt")) or signer.signed_at or datetime.utcnow()
        if signer.status == "declined":
            signer.declined_at = signer.declined_at or datetime.utcnow()


def _store(signature: LeaseSignature, name: str, content: bytes) -> str:
    path = folder(signature.lease) / f"{name}-{signature.id}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return str(path.relative_to(instance_dir()))


def refresh(signature: LeaseSignature, client: documenso.Client | None = None) -> LeaseSignature:
    """Lit l'état de l'envoi chez Documenso ; signé : PDF signé et journal d'audit rangés (commit)."""
    if signature.status != "sent":
        return signature
    client = client or documenso.Client.from_config()
    signature.checked_at = datetime.utcnow()
    try:
        remote = client.envelope(signature.submission_id)
        _apply_recipients(signature, remote)
        status = ENVELOPE_STATUS.get(remote.get("status"))
        if status == "declined" or any(s.status == "declined" for s in signature.signers):
            signature.status = "declined"
        elif status == "completed":
            items = remote.get("envelopeItems") or []
            if items:
                signature.signed_pdf_path = _store(signature, "bail-signe", client.download_signed(items[0]["id"]))
            signature.audit_pdf_path = _store(signature, "journal-audit", client.audit_log(signature.submission_id))
            signature.status = "completed"
            signature.completed_at = _when(remote.get("completedAt")) or datetime.utcnow()
        elif status == "cancelled":  # annulé depuis Documenso
            signature.status = "cancelled"
        signature.error = None
    except documenso.DocumensoError as exc:
        signature.error = exc.message
        db.session.commit()
        raise SaleError(exc.message, status=502) from None
    db.session.commit()
    return signature


def refresh_if_due(lease: Lease) -> None:
    """À l'ouverture du bail : statut relu au plus une fois par minute ; une erreur est seulement
    gardée sur l'envoi (le bail s'affiche quand même)."""
    signature = current(lease)
    if signature is None or signature.status != "sent":
        return
    if signature.checked_at and datetime.utcnow() - signature.checked_at < REFRESH_EVERY:
        return
    try:
        refresh(signature)
    except SaleError:
        pass


def cancel(signature: LeaseSignature, client: documenso.Client | None = None) -> None:
    """Annule l'envoi en cours chez Documenso : le bail redevient modifiable."""
    if signature.status != "sent":
        raise SaleError("Seul un envoi en cours s'annule.", status=409)
    try:
        (client or documenso.Client.from_config()).cancel(signature.submission_id)
    except documenso.DocumensoError as exc:
        raise SaleError(exc.message, status=502) from None
    signature.status = "cancelled"
    db.session.commit()


def file_path(signature: LeaseSignature, kind: str):
    relative = {"sent": signature.sent_pdf_path, "signed": signature.signed_pdf_path,
                "audit": signature.audit_pdf_path}.get(kind)
    path = (instance_dir() / relative) if relative else None
    return path if path is not None and path.is_file() else None
