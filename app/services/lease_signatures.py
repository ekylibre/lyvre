"""Signature électronique des baux (lot L4, BF13–BF17) avec Docuseal.

- Signataires : les **gérants** (registre des associés, case « Gérant », e-mail de leur fiche tiers),
  dans l'ordre du registre, puis le **preneur** (e-mail de sa fiche, sinon premier e-mail de
  facturation) ; Docuseal les sollicite dans cet ordre.
- Envoi : le PDF du bail est figé (`baux/<bail>/bail-envoye-<n>.pdf`) avec, dans chaque case du bloc de
  signatures, une balise de champ Docuseal (`{{…;role=…;type=signature}}`).
- Suivi : `refresh` lit l'état de l'envoi ; signé, le PDF signé et le journal d'audit sont rangés
  avec le bail. Un bail envoyé (ou signé) n'est plus modifiable dans ses termes ; annuler l'envoi le
  rend modifiable (BF17).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from markupsafe import escape

from app.extensions import db
from app.models import Associate, Lease, LeaseSignature, LeaseSigner
from app.services import docuseal, lease_documents
from app.services.attachments import instance_dir
from app.services.lease_map import folder
from app.services.sale_entry import SaleError

STATUS_LABELS = {"sent": "Envoyé à la signature", "completed": "Signé", "declined": "Signature refusée",
                 "expired": "Envoi expiré", "cancelled": "Envoi annulé"}
SIGNER_LABELS = {"awaiting": "En attente", "sent": "Invitation envoyée", "opened": "Ouvert", "completed": "Signé",
                 "declined": "Refusé"}
REFRESH_EVERY = timedelta(minutes=1)
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
    """Balises Docuseal dans les cases du bloc de signatures ; une page de signatures en plus pour les
    signataires sans case (texte rédigé avant le lot L4, gérants ajoutés depuis)."""
    by_key = {s["key"]: s for s in signers}

    def tag(signer):
        # Balise sur une seule ligne (Docuseal la lit dans le texte du PDF) : nom de champ court.
        return (f'<div class="sign-box"><span class="sign-tag">{{{{Signature {signer["key"].upper()};'
                f'role={escape(signer["role"])};type=signature;width=170;height=55}}}}</span></div>')

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


def send(lease: Lease, user_id=None, client: docuseal.Client | None = None) -> LeaseSignature:
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
    client = client or docuseal.Client.from_config()
    number = len(lease.signatures) + 1
    path = folder(lease) / f"bail-envoye-{number}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pdf)
    name = f"Bail {lease.unit_label} — {lease.entity.name}"[:200]
    try:
        data = client.create_submission(name, pdf, [
            {"role": s["role"], "email": s["email"], "name": s["name"], "external_id": f"lease-{lease.id}-{s['key']}"}
            for s in signers], external_id=f"lease-{lease.id}")
    except docuseal.DocusealError as exc:
        path.unlink(missing_ok=True)
        raise SaleError(exc.message, status=502) from None
    submitters = {s.get("role"): s for s in data.get("submitters") or []}
    submission_id = data.get("id") or next((s.get("submission_id") for s in submitters.values()), None)
    signature = LeaseSignature(lease=lease, submission_id=str(submission_id or ""), status="sent",
                               sent_at=datetime.utcnow(), checked_at=datetime.utcnow(), created_by_id=user_id,
                               sent_pdf_path=str(path.relative_to(instance_dir())))
    for position, s in enumerate(signers):
        remote = submitters.get(s["role"]) or {}
        signature.signers.append(LeaseSigner(
            position=position, role=s["role"], name=s["name"], email=s["email"], associate_id=s["associate_id"],
            entity_id=s["entity_id"], submitter_id=str(remote.get("id") or "") or None,
            status=remote.get("status") if remote.get("status") in SIGNER_LABELS else "awaiting"))
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


def _store(signature: LeaseSignature, name: str, content: bytes) -> str:
    path = folder(signature.lease) / f"{name}-{signature.id}.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return str(path.relative_to(instance_dir()))


def refresh(signature: LeaseSignature, client: docuseal.Client | None = None) -> LeaseSignature:
    """Lit l'état de l'envoi chez Docuseal ; signé : PDF signé et journal d'audit rangés (commit)."""
    if signature.status != "sent":
        return signature
    client = client or docuseal.Client.from_config()
    signature.checked_at = datetime.utcnow()
    try:
        data = client.submission(signature.submission_id)
        remote = {s.get("role"): s for s in data.get("submitters") or []}
        for signer in signature.signers:
            r = remote.get(signer.role) or {}
            if r.get("status") in SIGNER_LABELS:
                signer.status = r["status"]
            signer.signed_at = _when(r.get("completed_at")) or signer.signed_at
            signer.declined_at = _when(r.get("declined_at")) or signer.declined_at
        status = data.get("status")
        if any(s.status == "declined" for s in signature.signers) or status == "declined":
            signature.status = "declined"
        elif status == "completed" or (signature.signers and all(s.status == "completed" for s in signature.signers)):
            documents = client.documents(signature.submission_id)
            if documents:
                signature.signed_pdf_path = _store(signature, "bail-signe", client.download(documents[0]["url"]))
            if data.get("audit_log_url"):
                signature.audit_pdf_path = _store(signature, "journal-audit", client.download(data["audit_log_url"]))
            signature.status = "completed"
            signature.completed_at = _when(data.get("completed_at")) or datetime.utcnow()
        elif status == "expired":
            signature.status = "expired"
        signature.error = None
    except docuseal.DocusealError as exc:
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


def cancel(signature: LeaseSignature, client: docuseal.Client | None = None) -> None:
    """Annule l'envoi (archivé chez Docuseal) : le bail redevient modifiable."""
    if signature.status != "sent":
        raise SaleError("Seul un envoi en cours s'annule.", status=409)
    try:
        (client or docuseal.Client.from_config()).archive(signature.submission_id)
    except docuseal.DocusealError as exc:
        raise SaleError(exc.message, status=502) from None
    signature.status = "cancelled"
    db.session.commit()


def file_path(signature: LeaseSignature, kind: str):
    relative = {"sent": signature.sent_pdf_path, "signed": signature.signed_pdf_path,
                "audit": signature.audit_pdf_path}.get(kind)
    path = (instance_dir() / relative) if relative else None
    return path if path is not None and path.is_file() else None
