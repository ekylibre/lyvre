"""Décomptes de coopérative (lot AG10.d, claudedocs/design_efacturation_agricole.md § 4, AGD27).

Pièce composée d'une coopérative, d'une laiterie ou d'un négociant : apports, compléments de prix et ristournes
(ventes 70x), acomptes déjà versés, parts sociales retenues (2621), cotisations et frais (62x / 63x). Une seule
écriture équilibrée sur le compte client (411) du tiers ; voir `app/services/coop_statements.py`."""
from datetime import datetime

from app.extensions import db

# Type de ligne : (libellé, sens dans l'écriture). « credit » : produit ; « debit » : retenue ; None : sans écriture.
LINE_KINDS = {
    "delivery": ("Apport", "credit"),
    "complement": ("Complément de prix", "credit"),
    "rebate": ("Ristourne", "credit"),
    "advance": ("Acompte déjà versé", None),
    "shares": ("Parts sociales retenues", "debit"),
    "fee": ("Cotisation, frais, prélèvement", "debit"),
}
SALE_KINDS = ("delivery", "complement", "rebate")
STATUSES = {"draft": "Brouillon", "posted": "Comptabilisé"}


class CoopStatement(db.Model):
    __tablename__ = "coop_statements"
    __table_args__ = (db.UniqueConstraint("entity_id", "number", name="uq_coop_statements_entity_number"),)

    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False, index=True)
    number = db.Column(db.String(40), nullable=False)
    statement_date = db.Column(db.Date, nullable=False)
    label = db.Column(db.String(200))
    status = db.Column(db.String(8), nullable=False, default="draft")
    journal_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    journal_id = db.Column(db.Integer, db.ForeignKey("journals.id", ondelete="SET NULL"))   # vide : journal des ventes
    attachment_path = db.Column(db.String(300))
    attachment_name = db.Column(db.String(200))
    attachment_mime = db.Column(db.String(50))
    attachment_size = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    entity = db.relationship("Entity")
    journal_entry = db.relationship("JournalEntry")
    journal = db.relationship("Journal")
    lines = db.relationship("CoopStatementLine", back_populates="statement", cascade="all, delete-orphan",
                            order_by="CoopStatementLine.position")


class CoopStatementLine(db.Model):
    __tablename__ = "coop_statement_lines"

    id = db.Column(db.Integer, primary_key=True)
    statement_id = db.Column(db.Integer, db.ForeignKey("coop_statements.id", ondelete="CASCADE"), nullable=False, index=True)
    position = db.Column(db.Integer, nullable=False, default=0)
    kind = db.Column(db.String(10), nullable=False)
    label = db.Column(db.String(200), nullable=False)
    quantity_milli = db.Column(db.Integer)
    unit = db.Column(db.String(20))
    amount_cents = db.Column(db.Integer, nullable=False)        # HT, positif
    vat_rate_bp = db.Column(db.Integer, nullable=False, default=0)
    vat_cents = db.Column(db.Integer, nullable=False, default=0)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="SET NULL"))
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id", ondelete="SET NULL"))
    campaign_year = db.Column(db.Integer)                      # campagne de l'apport ou d'origine du complément

    statement = db.relationship("CoopStatement", back_populates="lines")
    account = db.relationship("Account")
    activity = db.relationship("Activity")
