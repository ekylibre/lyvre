"""Contrôle des aides avec les montants publiés par l'ASP (lot AG3.e, claudedocs/design_aides_pac.md § 7, AG3.5).

Pour une année : total publié (FEAGA + FEADER + cofinancé, Lexicon `cap_beneficiaries`) contre
- les versements rattachés aux dossiers d'aide, datés de l'année civile ;
- les mouvements des comptes de subventions (74 sauf 741 et 747, et 131) de l'année civile, hors écritures de clôture
  (inventaire, extournes, à-nouveaux, octrois, reprises).
L'année publiée est une année de paiement de l'UE, ni un exercice ni une campagne : l'écart est une **information**.
Jamais de cumul entre années. Montants publiés gardés dans `cap_published` (cache de l'instance), relus à la demande.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func

from app.extensions import db
from app.models import Account, AidPayment, CapPublished, JournalEntry, JournalLine
from app.models.journal_entry import (
    SOURCE_AID_GRANT, SOURCE_AID_RELEASE, SOURCE_CLOSING, SOURCE_INVENTORY, SOURCE_OPENING, SOURCE_REVERSAL,
)
from app.services import lexicon
from app.services.aids import AidError

EXCLUDED = (SOURCE_INVENTORY, SOURCE_REVERSAL, SOURCE_OPENING, SOURCE_CLOSING, SOURCE_AID_GRANT, SOURCE_AID_RELEASE)


def _siren() -> str | None:
    from app.services import organization
    siren = (organization.get().siren or "").replace(" ", "")
    return siren or None


def refresh(siren: str) -> int:
    """Relit Lexicon et remplace le cache du SIREN (sans commit) ; nombre d'années publiées."""
    rows = lexicon.cap_by_year(siren)
    CapPublished.query.filter_by(siren=siren).delete()
    now = datetime.utcnow()
    for row in rows or []:
        db.session.add(CapPublished(siren=siren, fetched_at=now, **row))
    db.session.flush()
    return len(rows or [])


def _ledger_cents(year: int) -> int:
    start, end = date(year, 1, 1), date(year, 12, 31)
    account_filter = db.or_(db.and_(Account.code.like("74%"), ~Account.code.like("741%"), ~Account.code.like("747%")),
                            Account.code.like("131%"))
    total = (db.session.query(func.coalesce(func.sum(JournalLine.credit_cents - JournalLine.debit_cents), 0))
             .join(Account, Account.id == JournalLine.account_id)
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .filter(JournalEntry.entry_date.between(start, end), account_filter,
                     db.or_(JournalEntry.source.is_(None), JournalEntry.source.notin_(EXCLUDED))).scalar())
    return int(total or 0)


def _paid_cents(year: int) -> int:
    total = (db.session.query(func.coalesce(func.sum(AidPayment.amount_cents), 0))
             .filter(AidPayment.paid_on.between(date(year, 1, 1), date(year, 12, 31))).scalar())
    return int(total or 0)


def check(year: int, force: bool = False) -> dict:
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        raise AidError("Année attendue.", "year")
    siren = _siren()
    out = {"year": year, "configured": lexicon.configured(), "siren": siren, "published": None, "years": [],
           "fetched_at": None, "found": None, "paid_cents": _paid_cents(year), "ledger_cents": _ledger_cents(year),
           "message": None}
    if not out["configured"]:
        out["message"] = "Lexicon n'est pas configuré sur ce serveur : contrôle indisponible."
        return out
    if siren is None:
        out["message"] = "Renseignez le SIREN de l'exploitation (Structure › Organisation) pour lire les aides publiées."
        return out
    cached = CapPublished.query.filter_by(siren=siren).all()
    if force or not cached:
        try:
            count = refresh(siren)
            db.session.commit()
        except lexicon.LexiconUnavailable as exc:
            db.session.rollback()
            out["message"] = exc.message
            count = None
        cached = CapPublished.query.filter_by(siren=siren).all()
        if count is not None:
            out["found"] = count > 0
    by_year = {c.year: c for c in cached}
    out["years"] = sorted(by_year, reverse=True)
    row = by_year.get(year)
    if cached:
        out["fetched_at"] = max(c.fetched_at for c in cached).isoformat(timespec="seconds")
    if row is not None:
        out["published"] = {"feaga_cents": row.feaga_cents, "feader_cents": row.feader_cents,
                            "cofinanced_cents": row.cofinanced_cents, "total_cents": row.total_cents}
        out["gap_paid_cents"] = out["paid_cents"] - row.total_cents
        out["gap_ledger_cents"] = out["ledger_cents"] - row.total_cents
    elif out["message"] is None:
        out["message"] = (f"Aucune aide publiée pour {year} sous ce SIREN." if cached or out["found"] is False
                          else "Aucune donnée publiée lue pour ce SIREN.")
    return out
