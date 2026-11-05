"""Associés d'une société (module « Associés », claudedocs/design_associes.md).

Un associé est une entité (tiers) avec un compte courant, sous-compte 455 dont le solde se lit
dans le grand livre. Le registre des parts est une suite de mouvements datés ; la situation à une
date est la somme des variations jusqu'à cette date (hors comptabilité).
"""
from datetime import datetime

from app.extensions import db

PART_NATURES = [("full", "Pleine propriété"), ("usufruct", "Usufruit"), ("bare", "Nue-propriété")]
MOVEMENT_KINDS = [
    ("opening", "Reprise"), ("subscription", "Souscription"), ("transfer", "Cession"),
    ("donation", "Donation"), ("succession", "Succession"), ("reunion", "Réunion de l'usufruit"),
    ("reduction", "Réduction de capital"),
]


class Associate(db.Model):
    __tablename__ = "associates"

    id = db.Column(db.Integer, primary_key=True)
    entity_id = db.Column(db.Integer, db.ForeignKey("entities.id", ondelete="RESTRICT"),
                          unique=True, nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id", ondelete="RESTRICT"),
                           unique=True, nullable=False)
    interest_rate_bp = db.Column(db.Integer)  # None : taux de la structure
    is_manager = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())  # gérant
    # Exploitation agricole (lot AG6.a) : associé exploitant, première aide JA, part des droits aux bénéfices (statuts).
    is_operator = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    young_farmer_since = db.Column(db.Date)
    profit_share_bp = db.Column(db.Integer)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    entity = db.relationship("Entity")
    account = db.relationship("Account")

    @property
    def name(self) -> str:
        return self.entity.name


class ShareMovement(db.Model):
    __tablename__ = "share_movements"

    id = db.Column(db.Integer, primary_key=True)
    movement_date = db.Column(db.Date, nullable=False, index=True)
    kind = db.Column(db.String(20), nullable=False)
    nominal_cents = db.Column(db.Integer)  # valeur d'une part (reprise, souscription, réduction)
    price_cents = db.Column(db.Integer)    # prix ou valeur déclarée, informatif
    description = db.Column(db.Text)
    attachment_path = db.Column(db.String(300))
    attachment_name = db.Column(db.String(200))
    attachment_mime = db.Column(db.String(50))
    attachment_size = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_by_id = db.Column(db.Integer)  # utilisateur (base méta), sans clé étrangère

    lines = db.relationship("ShareMovementLine", back_populates="movement", cascade="all, delete-orphan",
                            order_by="ShareMovementLine.id")


class ShareMovementLine(db.Model):
    __tablename__ = "share_movement_lines"

    id = db.Column(db.Integer, primary_key=True)
    movement_id = db.Column(db.Integer, db.ForeignKey("share_movements.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    associate_id = db.Column(db.Integer, db.ForeignKey("associates.id", ondelete="RESTRICT"),
                             nullable=False, index=True)
    nature = db.Column(db.String(10), nullable=False)  # full | usufruct | bare
    parts = db.Column(db.Integer, nullable=False)      # signé : + reçoit, − cède

    movement = db.relationship("ShareMovement", back_populates="lines")
    associate = db.relationship("Associate")


class AssociateExpense(db.Model):
    """Dépense avancée par un associé sans facture (note de frais) : charge / 455 de l'associé."""
    __tablename__ = "associate_expenses"

    id = db.Column(db.Integer, primary_key=True)
    associate_id = db.Column(db.Integer, db.ForeignKey("associates.id", ondelete="RESTRICT"),
                             nullable=False, index=True)
    expense_date = db.Column(db.Date, nullable=False)
    label = db.Column(db.String(255), nullable=False)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    untaxed_cents = db.Column(db.Integer, nullable=False)
    vat_rate_bp = db.Column(db.Integer)
    vat_cents = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    total_cents = db.Column(db.Integer, nullable=False)
    attachment_path = db.Column(db.String(300))
    attachment_name = db.Column(db.String(200))
    attachment_mime = db.Column(db.String(50))
    attachment_size = db.Column(db.Integer)
    journal_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    associate = db.relationship("Associate")
    account = db.relationship("Account")
    journal_entry = db.relationship("JournalEntry")
