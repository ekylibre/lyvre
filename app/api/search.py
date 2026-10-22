"""Recherche de la palette de commandes (Ctrl+K) : tiers, factures d'achat, écritures."""
from flask import jsonify, request, url_for

from app.extensions import db
from app.models import Entity, JournalEntry, Purchase

from . import bp

PER_GROUP = 5


@bp.route("/search")
def search():
    """`?q=` (2 caractères au moins) → `{"groups": [{"label", "items": [{label, description, url}]}]}`."""
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify(groups=[])
    like = f"%{q.lower()}%"
    entities = (Entity.query.filter(db.or_(db.func.lower(Entity.name).like(like),
                                           db.func.lower(Entity.email).like(like)))
                .order_by(Entity.name).limit(PER_GROUP).all())
    purchases = (Purchase.query.filter(db.or_(db.func.lower(Purchase.invoice_number).like(like),
                                              db.func.lower(Purchase.supplier_name).like(like)))
                 .order_by(Purchase.issue_date.desc().nullslast()).limit(PER_GROUP).all())
    entries = (JournalEntry.query.filter(db.or_(db.func.lower(JournalEntry.reference).like(like),
                                                db.func.lower(JournalEntry.description).like(like)))
               .order_by(JournalEntry.entry_date.desc()).limit(PER_GROUP).all())
    groups = [
        {"label": "Tiers", "items": [
            {"label": e.name, "description": e.email or e.entity_type,
             "url": url_for("entities.detail", entity_id=e.id)} for e in entities]},
        {"label": "Factures d'achat", "items": [
            {"label": f"{'Avoir' if p.is_credit_note else 'Facture'} {p.invoice_number or 'sans numéro'}",
             "description": " · ".join(filter(None, (p.supplier_name, p.issue_date.strftime("%d/%m/%Y")
                                                     if p.issue_date else None))),
             "url": url_for("purchases.detail", purchase_id=p.id)} for p in purchases]},
        {"label": "Écritures", "items": [
            {"label": f"{e.reference or 'Écriture'} — {e.description or ''}".strip(" —"),
             "description": e.entry_date.strftime("%d/%m/%Y"),
             "url": url_for("entries.detail", entry_id=e.id)} for e in entries]},
    ]
    return jsonify(groups=[g for g in groups if g["items"]])
