"""Modèles HelloAsso (API v5).

Hiérarchie HelloAsso :
- Form     : un formulaire (adhésion, billetterie, don récurrent, …)
- Order    : une commande passée par un payeur sur un Form
- Item     : un article d'une commande (adhésion, billet, don, …)
- Payment  : un règlement d'une commande (carte, prélèvement, …)
"""
from datetime import datetime

from app.extensions import db


HA_ITEM_TYPES = [
    ("Membership", "Adhésion"),
    ("Donation", "Don"),
    ("Payment", "Paiement"),
    ("Registration", "Inscription"),
    ("Product", "Produit"),
    ("Other", "Autre"),
]


class HelloAssoForm(db.Model):
    __tablename__ = "helloasso_forms"

    id = db.Column(db.Integer, primary_key=True)
    helloasso_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    form_slug = db.Column(db.String(200), index=True)
    form_type = db.Column(db.String(40))
    title = db.Column(db.String(300))
    organization_slug = db.Column(db.String(200))
    state = db.Column(db.String(40))
    raw_payload = db.Column(db.Text)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)


class HelloAssoOrder(db.Model):
    __tablename__ = "helloasso_orders"

    id = db.Column(db.Integer, primary_key=True)
    helloasso_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    form_id = db.Column(
        db.Integer,
        db.ForeignKey("helloasso_forms.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_id = db.Column(
        db.Integer,
        db.ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    date = db.Column(db.DateTime, index=True)
    amount_total_cents = db.Column(db.Integer, nullable=False, default=0)
    amount_vat_cents = db.Column(db.Integer, nullable=False, default=0)
    payer_first_name = db.Column(db.String(200))
    payer_last_name = db.Column(db.String(200))
    payer_email = db.Column(db.String(200), index=True)
    form_slug = db.Column(db.String(200))
    form_type = db.Column(db.String(40))
    organization_slug = db.Column(db.String(200))
    raw_payload = db.Column(db.Text)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)

    form = db.relationship("HelloAssoForm")
    entity = db.relationship("Entity", foreign_keys=[entity_id])
    items = db.relationship(
        "HelloAssoItem", backref="order",
        cascade="all, delete-orphan", passive_deletes=True, lazy="dynamic",
    )
    payments = db.relationship(
        "HelloAssoPayment", backref="order",
        cascade="all, delete-orphan", passive_deletes=True, lazy="dynamic",
    )


class HelloAssoItem(db.Model):
    __tablename__ = "helloasso_items"

    id = db.Column(db.Integer, primary_key=True)
    helloasso_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("helloasso_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id = db.Column(
        db.Integer,
        db.ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name = db.Column(db.String(300))
    type = db.Column(db.String(40))
    state = db.Column(db.String(40))
    amount_cents = db.Column(db.Integer, nullable=False, default=0)
    user_first_name = db.Column(db.String(200))
    user_last_name = db.Column(db.String(200))
    user_email = db.Column(db.String(200), index=True)
    raw_payload = db.Column(db.Text)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)

    entity = db.relationship("Entity", foreign_keys=[entity_id])


class HelloAssoPayment(db.Model):
    __tablename__ = "helloasso_payments"

    id = db.Column(db.Integer, primary_key=True)
    helloasso_id = db.Column(db.Integer, unique=True, nullable=False, index=True)
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("helloasso_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount_cents = db.Column(db.Integer, nullable=False, default=0)
    state = db.Column(db.String(40))
    payment_means = db.Column(db.String(40))
    payment_date = db.Column(db.DateTime, index=True)
    payer_email = db.Column(db.String(200), index=True)
    raw_payload = db.Column(db.Text)
    imported_at = db.Column(db.DateTime, default=datetime.utcnow)
