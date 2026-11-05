"""Cotisations MSA des non-salariés agricoles (lot AG7, claudedocs/design_msa.md, AGD24)."""
from __future__ import annotations

from datetime import datetime

from app.extensions import db

MSA_STATUSES = {"principal": "Chef d'exploitation à titre exclusif ou principal",
                "secondary": "Chef d'exploitation à titre secondaire",
                "collaborator": "Collaborateur d'exploitation"}
MSA_BASE_OPTIONS = {"triennial": "Moyenne triennale (droit commun)", "annual": "Assiette annuelle (revenus N-1, option)"}
MSA_ADJUSTMENT_KINDS = {"avaloir": "À-valoir social (art. 72 F) déduit", "add": "Autre réintégration",
                        "deduct": "Autre déduction"}


class MsaPerson(db.Model):
    """Exploitant suivi pour la MSA : l'exploitant de l'EI (associé nul) ou un associé exploitant de la société."""
    __tablename__ = "msa_people"

    id = db.Column(db.Integer, primary_key=True)
    associate_id = db.Column(db.Integer, db.ForeignKey("associates.id", ondelete="CASCADE"), unique=True)
    status = db.Column(db.String(12), nullable=False, default="principal", server_default="principal")
    base_option = db.Column(db.String(10), nullable=False, default="triennial", server_default="triennial")
    option_since = db.Column(db.Date)
    atexa_category = db.Column(db.String(1))                                   # A à E (lot AG7.e)
    note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    associate = db.relationship("Associate")


class MsaBase(db.Model):
    """Assiette sociale d'une année de revenus : calculée par Lyvre (figée à la clôture) ou saisie depuis l'avis MSA."""
    __tablename__ = "msa_bases"

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey("msa_people.id", ondelete="CASCADE"), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    source = db.Column(db.String(8), nullable=False, default="lyvre")        # lyvre | entered
    income_cents = db.Column(db.Integer)                                       # revenu avant abattement
    abatement_cents = db.Column(db.Integer)
    base_cents = db.Column(db.Integer, nullable=False)
    detail_json = db.Column(db.Text)
    note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (db.UniqueConstraint("person_id", "year", name="uq_msa_bases_person_year"),)


class MsaAdjustment(db.Model):
    """Ligne saisie du passage à l'assiette sociale : à-valoir 72 F, autre réintégration ou déduction (motif)."""
    __tablename__ = "msa_adjustments"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, index=True)
    person_id = db.Column(db.Integer, db.ForeignKey("msa_people.id", ondelete="CASCADE"), nullable=False)
    kind = db.Column(db.String(10), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(300))


MSA_CALL_KINDS = {"first": "1er appel provisionnel", "second": "2e appel provisionnel", "balance": "Solde",
                  "monthly": "Mensualité", "single": "Appel unique", "regularization": "Régularisation"}


class MsaCall(db.Model):
    """Appel de cotisations reçu (avis d'appel ou relevé MSA), avec son détail et le paiement rapproché (lot AG7.c)."""
    __tablename__ = "msa_calls"

    id = db.Column(db.Integer, primary_key=True)
    person_id = db.Column(db.Integer, db.ForeignKey("msa_people.id", ondelete="CASCADE"), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False, index=True)                   # année de cotisation
    kind = db.Column(db.String(14), nullable=False)
    due_on = db.Column(db.Date, nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    base_cents = db.Column(db.Integer)                                          # assiette indiquée sur l'avis
    contributions_cents = db.Column(db.Integer)
    csg_deductible_cents = db.Column(db.Integer)
    csg_crds_non_deductible_cents = db.Column(db.Integer)
    third_party_cents = db.Column(db.Integer)
    estimated = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    bank_transaction_id = db.Column(db.Integer, db.ForeignKey("bank_transactions.id", ondelete="SET NULL"))
    journal_entry_id = db.Column(db.Integer, db.ForeignKey("journal_entries.id", ondelete="SET NULL"))
    note = db.Column(db.String(300))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    person = db.relationship("MsaPerson")
    bank_transaction = db.relationship("BankTransaction")
