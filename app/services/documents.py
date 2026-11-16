"""Navigateur des documents de l'instance (lot NV5, claudedocs/design_navigation.md § 6).

Registre de **sources** : chaque source décrit un type de document et liste les fichiers déjà stockés, à partir des
colonnes existantes, sans rien copier. Le lien de téléchargement est la **route existante** de la source, avec ses
contrôles de droits ; aucune nouvelle porte d'accès n'est ouverte (F11). Tous les rôles de l'instance lisent ces
fiches ; seules les options de l'instance (associés) restreignent la liste.

Hors périmètre (Q4) : pièces Qonto et Documenso distantes, dépôt de documents libres, logo et signature.
"""
from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Iterable

from flask import current_app

from app.extensions import db
from app.models import FiscalYear

PAGE_SIZE = 50


@dataclass
class Doc:
    kind: str
    name: str
    date: date | None
    file_url: str
    origin_label: str
    origin_url: str
    party: str | None = None
    mime: str | None = None
    size: int | None = None
    path: Callable[[], Path | None] | None = field(default=None, repr=False)  # taille calculée à l'affichage
    fiscal_year: FiscalYear | None = None


@dataclass
class Source:
    kind: str
    label: str
    icon: str
    rows: Callable[[], Iterable[Doc]]
    enabled: Callable[[], bool] = lambda: True
    pictogram: str | None = None


def _day(value) -> date | None:
    return value.date() if isinstance(value, datetime) else value


def _instance_file(relative: str | None) -> Callable[[], Path | None]:
    def resolve():
        from app.services.attachments import AttachmentError, _within, instance_dir
        if not relative:
            return None
        try:
            path = _within(instance_dir() / relative, instance_dir())
        except AttachmentError:
            return None
        return path if path.is_file() else None
    return resolve


def _app_file(relative: str | None) -> Callable[[], Path | None]:
    def resolve():
        if not relative:
            return None
        root = Path(current_app.instance_path).resolve()
        path = (root / relative).resolve()
        return path if path.is_relative_to(root) and path.is_file() else None
    return resolve


# --------------------------------------------------------------------------- sources
def _purchases():
    from app.models import Purchase
    for p in Purchase.query.filter(Purchase.attachment_path.isnot(None)):
        yield Doc("purchase", p.attachment_name or f"facture-{p.id}", p.issue_date, f"/purchases/{p.id}/attachment",
                  f"Facture d'achat {p.invoice_number or p.id}", f"/purchases/{p.id}", party=p.supplier_name,
                  mime=p.attachment_mime, size=p.attachment_size)


def _sales():
    from app.models import Sale
    from app.services import sale_documents
    for s in Sale.query.filter(Sale.pdf_path.isnot(None)):
        yield Doc("sale", sale_documents.filename(s), s.issue_date, f"/api/v1/sales/{s.id}/pdf",
                  f"Pièce {s.number or s.id}", f"/sales/{s.id}", party=s.entity.name if s.entity else None,
                  mime="application/pdf", path=_instance_file(s.pdf_path))


def _self_billed():
    from app.models import Sale
    for s in Sale.query.filter(Sale.self_billed.is_(True), Sale.received_file.isnot(None)):
        name = Path(s.received_file).name
        yield Doc("self_billed", name, s.issue_date, f"/api/v1/sales/{s.id}/received-file",
                  f"Autofacture {s.number or s.id}", f"/sales/{s.id}", party=s.entity.name if s.entity else None,
                  mime=mimetypes.guess_type(name)[0], path=_instance_file(s.received_file))


def _coop_statements():
    from app.models import CoopStatement
    for c in CoopStatement.query.filter(CoopStatement.attachment_path.isnot(None)):
        yield Doc("coop_statement", c.attachment_name or f"decompte-{c.number}", c.statement_date,
                  f"/api/v1/coop-statements/{c.id}/attachment", f"Décompte {c.number}", "/sales/coop-statements",
                  party=c.entity.name if c.entity else None, mime=c.attachment_mime, size=c.attachment_size)


def _donation_receipts():
    from app.models import DonationReceipt
    for r in DonationReceipt.query.filter(DonationReceipt.pdf_path.isnot(None)):
        yield Doc("donation_receipt", f"recu-{r.number}.pdf", _day(r.issued_at), f"/receipts/{r.id}.pdf",
                  f"Reçu fiscal {r.number}", "/receipts/", party=r.entity.name if r.entity else None,
                  mime="application/pdf", path=_instance_file(r.pdf_path))


def _bank_statements():
    from app.models import BankStatement
    for b in BankStatement.query.filter(BankStatement.replaced_at.is_(None)):
        account = b.bank_account
        yield Doc("bank_statement", b.file_name or f"releve-{b.period:%Y-%m}.pdf", b.period,
                  f"/bank-statements/{b.id}.pdf", f"Relevé {account.label if account else ''} {b.period:%m/%Y}".strip(),
                  f"/bank-accounts/{b.bank_account_id}/transactions", party=account.label if account else None,
                  mime="application/pdf", size=b.file_size or None)


def _rent_receipts():
    from app.models import RentReceipt
    for r in RentReceipt.query.filter(RentReceipt.pdf_path.isnot(None)):
        lease = r.lease
        yield Doc("lease", Path(r.pdf_path).name, r.period_start or _day(r.created_at),
                  f"/api/v1/rent-receipts/{r.id}/pdf", "Quittance" if r.kind == "quittance" else "Reçu de loyer",
                  f"/leases/{r.lease_id}", party=lease.entity.name if lease and lease.entity else None,
                  mime="application/pdf", path=_instance_file(r.pdf_path))


def _lease_signatures():
    from app.models import LeaseSignature
    names = {"sent": "Bail envoyé", "signed": "Bail signé", "audit": "Certificat de signature"}
    for s in LeaseSignature.query.all():
        lease = s.lease
        for kind, relative in (("sent", s.sent_pdf_path), ("signed", s.signed_pdf_path), ("audit", s.audit_pdf_path)):
            if relative:
                yield Doc("lease", Path(relative).name, _day(s.completed_at or s.sent_at),
                          f"/api/v1/lease-signatures/{s.id}/{kind}.pdf", names[kind], f"/leases/{s.lease_id}",
                          party=lease.entity.name if lease and lease.entity else None, mime="application/pdf",
                          path=_instance_file(relative))


def _associates_on() -> bool:
    from app.services import associates
    return associates.enabled()


def _share_movements():
    from app.models import ShareMovement
    for m in ShareMovement.query.filter(ShareMovement.attachment_path.isnot(None)):
        yield Doc("share_movement", m.attachment_name or f"mouvement-{m.id}", m.movement_date,
                  f"/api/v1/share-movements/{m.id}/attachment", "Mouvement de parts", "/share-movements/",
                  mime=m.attachment_mime, size=m.attachment_size)


def _associate_expenses():
    from app.models import AssociateExpense
    for e in AssociateExpense.query.filter(AssociateExpense.attachment_path.isnot(None)):
        associate = e.associate
        yield Doc("associate_expense", e.attachment_name or f"note-{e.id}", e.expense_date,
                  f"/api/v1/associate-expenses/{e.id}/attachment", f"Note de frais : {e.label}", "/associate-expenses/",
                  party=getattr(associate, "name", None), mime=e.attachment_mime, size=e.attachment_size)


def _stock_counts():
    from app.models import StockCountFile
    for f in StockCountFile.query.filter(StockCountFile.attachment_path.isnot(None)):
        yield Doc("stock_count", f.attachment_name or f"comptage-{f.id}", _day(f.created_at),
                  f"/api/v1/fiscal-years/{f.fiscal_year_id}/stock/files/{f.id}", "Feuille de comptage",
                  f"/inventory/?fy_id={f.fiscal_year_id}", mime=f.attachment_mime, size=f.attachment_size,
                  fiscal_year=db.session.get(FiscalYear, f.fiscal_year_id))


def _rfa():
    from app.models import RfaAttestation
    for a in RfaAttestation.query.filter(RfaAttestation.attachment_path.isnot(None)):
        yield Doc("rfa", a.attachment_name or f"attestation-{a.year}", a.received_on or _day(a.created_at),
                  f"/api/v1/rfa/attestations/{a.id}/file", f"Attestation {a.year}", "/rfa/",
                  party=a.entity.name if a.entity else None, mime=a.attachment_mime, size=a.attachment_size)


def _fec():
    for fy in FiscalYear.query.filter(FiscalYear.fec_path.isnot(None)):
        yield Doc("fec", Path(fy.fec_path).name, fy.end_date, f"/fiscal-years/{fy.id}/fec", f"Exercice {fy.label}",
                  f"/fiscal-years/{fy.id}/closing", mime="text/plain", path=_app_file(fy.fec_path), fiscal_year=fy)


SOURCES = [
    Source("purchase", "Factures d'achat", "receipt", _purchases),
    Source("sale", "Factures, avoirs et devis", "file-text", _sales),
    Source("self_billed", "Autofactures reçues", "file-input", _self_billed, pictogram="barn"),
    Source("coop_statement", "Décomptes de coopérative", "scroll-text", _coop_statements, pictogram="barn"),
    Source("donation_receipt", "Reçus fiscaux", "file-heart", _donation_receipts),
    Source("bank_statement", "Relevés bancaires", "landmark", _bank_statements),
    Source("lease", "Baux et quittances", "key-round", lambda: [*_rent_receipts(), *_lease_signatures()]),
    Source("share_movement", "Mouvements de parts", "book-user", _share_movements, enabled=_associates_on),
    Source("associate_expense", "Notes de frais", "receipt-euro", _associate_expenses, enabled=_associates_on),
    Source("stock_count", "Feuilles de comptage", "boxes", _stock_counts, pictogram="silo"),
    Source("rfa", "Attestations RFA", "hand-coins", _rfa),
    Source("fec", "Exports réglementaires (FEC)", "file-chart-column", _fec),   # D-NV3
]
BY_KIND = {s.kind: s for s in SOURCES}


def _fy_for(day: date | None, years: list[FiscalYear]) -> FiscalYear | None:
    if day is None:
        return None
    return next((fy for fy in years if fy.start_date <= day <= fy.end_date), None)


def collect() -> list[Doc]:
    """Tous les documents des sources actives, rattachés à leur exercice."""
    years = FiscalYear.query.order_by(FiscalYear.start_date.desc()).all()
    docs = []
    for source in SOURCES:
        if not source.enabled():
            continue
        for doc in source.rows():
            doc.fiscal_year = doc.fiscal_year or _fy_for(doc.date, years)
            docs.append(doc)
    return docs


def _matches(doc: Doc, q: str) -> bool:
    return any(q in (value or "").casefold() for value in (doc.name, doc.party, doc.origin_label))


def browse(kind: str | None = None, fiscal_year_id: int | None = None, q: str | None = None, page: int = 1) -> dict:
    """Page de documents filtrés, triés par date décroissante, avec les compteurs par type et par exercice."""
    docs = collect()
    needle = (q or "").strip().casefold()
    if needle:
        docs = [d for d in docs if _matches(d, needle)]
    by_kind, by_year = {}, {}
    for d in docs:
        if fiscal_year_id is None or (d.fiscal_year and d.fiscal_year.id == fiscal_year_id):
            by_kind[d.kind] = by_kind.get(d.kind, 0) + 1
        if kind is None or d.kind == kind:
            key = d.fiscal_year.id if d.fiscal_year else None
            by_year[key] = by_year.get(key, 0) + 1
    if kind:
        docs = [d for d in docs if d.kind == kind]
    if fiscal_year_id is not None:
        docs = [d for d in docs if d.fiscal_year and d.fiscal_year.id == fiscal_year_id]
    docs.sort(key=lambda d: (d.date or date.min, d.name), reverse=True)
    page = max(page, 1)
    rows = docs[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    years = {fy.id: fy for fy in FiscalYear.query.all()}
    return {
        "items": [payload(d) for d in rows],
        "total": len(docs),
        "page": page,
        "page_size": PAGE_SIZE,
        "facets": {
            "kinds": [{"value": s.kind, "label": s.label, "icon": s.icon, "pictogram": s.pictogram,
                       "count": by_kind[s.kind]} for s in SOURCES if by_kind.get(s.kind)],
            "fiscal_years": sorted(
                ({"value": str(k) if k else "none", "label": years[k].label if k else "Hors exercice", "count": n}
                 for k, n in by_year.items()),
                key=lambda f: (f["value"] != "none", f["label"]), reverse=True),
        },
    }


def payload(doc: Doc) -> dict:
    size = doc.size
    if size is None and doc.path is not None:
        path = doc.path()
        size = path.stat().st_size if path else None
    mime = doc.mime or mimetypes.guess_type(doc.name)[0]
    source = BY_KIND[doc.kind]
    return {
        "id": doc.file_url, "kind": doc.kind, "kind_label": source.label, "name": doc.name,
        "date": doc.date.isoformat() if doc.date else None, "size": size, "mime": mime, "party": doc.party,
        "fiscal_year": {"id": doc.fiscal_year.id, "label": doc.fiscal_year.label} if doc.fiscal_year else None,
        "origin": {"label": doc.origin_label, "url": doc.origin_url}, "file_url": doc.file_url,
        "preview": bool(mime and (mime == "application/pdf" or mime.startswith("image/"))),
    }
