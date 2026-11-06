"""Analytique agricole par activité (lot AG8, claudedocs/design_analytique_agricole.md, AGD25) : atelier → activité →
production (activité × campagne, mesure physique)."""
from __future__ import annotations

from datetime import datetime

from app.extensions import db

ACTIVITY_FAMILIES = {"plant_farming": "Culture de plantes", "animal_farming": "Élevage", "vine_farming": "Viticulture",
                     "wine_making": "Vinification", "processing": "Transformation",
                     "service_delivering": "Prestations de service", "tool_maintaining": "Entretien d'outils",
                     "energy_production": "Production d'énergie", "environmental_service": "Services environnementaux",
                     "administering": "Administration"}
ACTIVITY_NATURES = {"main": "Principale", "auxiliary": "Auxiliaire (répartie)", "standalone": "Autonome (hors répartition)"}
ACTIVITY_CYCLES = {"annual": "Annuel", "perennial": "Pérenne"}
ACTIVITY_UNITS = {"hectare": "ha", "head": "têtes", "unity": "unités", "square_meter": "m²", "cubic_meter": "m³"}


class Workshop(db.Model):
    """Atelier : regroupe des activités (« Vaches laitières » : lait, génisses, veaux)."""
    __tablename__ = "workshops"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    family = db.Column(db.String(30), nullable=False)
    isacompta_code = db.Column(db.String(20))
    position = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    archived = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    activities = db.relationship("Activity", back_populates="workshop", order_by="Activity.name")


class Activity(db.Model):
    """Activité d'un atelier, rattachée ou non à une production Lexicon ; ses dates de cycle déterminent la campagne."""
    __tablename__ = "activities"

    id = db.Column(db.Integer, primary_key=True)
    workshop_id = db.Column(db.Integer, db.ForeignKey("workshops.id", ondelete="RESTRICT"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    lexicon_reference = db.Column(db.String(80))
    nature = db.Column(db.String(12), nullable=False, default="main", server_default="main")
    cycle = db.Column(db.String(10), nullable=False, default="annual", server_default="annual")
    unit = db.Column(db.String(14), nullable=False, default="hectare", server_default="hectare")
    cycle_start = db.Column(db.String(5), nullable=False, default="01-01", server_default="01-01")    # MM-JJ
    cycle_stop = db.Column(db.String(5), nullable=False, default="12-31", server_default="12-31")
    year_offset = db.Column(db.Integer, nullable=False, default=0, server_default="0")               # début en N − offset
    isacompta_code = db.Column(db.String(20))
    distribution_key_id = db.Column(db.Integer, db.ForeignKey("analytic_keys.id", ondelete="SET NULL"))  # auxiliaire (AG8.e)
    archived = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    workshop = db.relationship("Workshop", back_populates="activities")
    distribution_key = db.relationship("AnalyticKey", foreign_keys=[distribution_key_id])

    __table_args__ = (db.UniqueConstraint("workshop_id", "name", name="uq_activities_workshop_name"),)


class Campaign(db.Model):
    """Campagne : année de fin du cycle (année de récolte)."""
    __tablename__ = "campaigns"

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, nullable=False, unique=True)
    note = db.Column(db.String(300))


class ActivityProduction(db.Model):
    """Activité sur une campagne : mesure physique (surface, effectif) servant aux clés et aux ratios."""
    __tablename__ = "activity_productions"

    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    measure = db.Column(db.Numeric(14, 3))
    measure_source = db.Column(db.String(12), nullable=False, default="entered", server_default="entered")
    note = db.Column(db.String(300))

    activity = db.relationship("Activity")
    campaign = db.relationship("Campaign")

    __table_args__ = (db.UniqueConstraint("activity_id", "campaign_id", name="uq_activity_productions_activity_campaign"),)


KEY_BASES = {"surface": "Surface des activités", "headcount": "Effectif des activités",
             "percentage": "Pourcentages saisis", "gross_margin": "Marge brute (état des marges)"}
ALLOCATION_ORIGINS = {"manual": "saisie", "account": "règle de compte", "purchase": "ligne d'achat", "rule": "règle bancaire",
                      "simple": "opération simple", "aid": "dossier d'aide", "import": "reprise du dossier",
                      "coop": "décompte de coopérative"}


class AnalyticKey(db.Model):
    """Clé de répartition : surface ou effectif des activités membres, pourcentages saisis, ou marge brute (lot AG8.b)."""
    __tablename__ = "analytic_keys"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False, unique=True)
    basis = db.Column(db.String(14), nullable=False)
    note = db.Column(db.String(300))
    archived = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())

    members = db.relationship("AnalyticKeyMember", cascade="all, delete-orphan", order_by="AnalyticKeyMember.id")


class AnalyticKeyMember(db.Model):
    __tablename__ = "analytic_key_members"

    id = db.Column(db.Integer, primary_key=True)
    key_id = db.Column(db.Integer, db.ForeignKey("analytic_keys.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id", ondelete="CASCADE"), nullable=False)
    share_bp = db.Column(db.Integer)                                   # base « percentage »

    activity = db.relationship("Activity")


class AnalyticAllocation(db.Model):
    """Ventilation d'une ligne d'écriture sur une activité ou une clé (part en points de base), sans toucher l'écriture."""
    __tablename__ = "analytic_allocations"

    id = db.Column(db.Integer, primary_key=True)
    journal_line_id = db.Column(db.Integer, db.ForeignKey("journal_lines.id", ondelete="CASCADE"), nullable=False, index=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id", ondelete="CASCADE"))
    key_id = db.Column(db.Integer, db.ForeignKey("analytic_keys.id", ondelete="CASCADE"))
    campaign_year = db.Column(db.Integer)                              # vide : déduite des dates de l'activité
    share_bp = db.Column(db.Integer, nullable=False, default=10000)
    origin = db.Column(db.String(10), nullable=False, default="manual", server_default="manual")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    activity = db.relationship("Activity")
    key = db.relationship("AnalyticKey")
    journal_line = db.relationship("JournalLine", backref=db.backref("analytic_allocations", cascade="all, delete-orphan"))


class AnalyticRule(db.Model):
    """Affectation par défaut des lignes d'un compte (préfixe le plus long) : activité ou clé (lot AG8.b)."""
    __tablename__ = "analytic_rules"

    id = db.Column(db.Integer, primary_key=True)
    account_prefix = db.Column(db.String(20), nullable=False, unique=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id", ondelete="CASCADE"))
    key_id = db.Column(db.Integer, db.ForeignKey("analytic_keys.id", ondelete="CASCADE"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    activity = db.relationship("Activity")
    key = db.relationship("AnalyticKey")


class AnalyticSnapshot(db.Model):
    """État des marges figé à la clôture définitive de l'exercice (lot AG8.e)."""
    __tablename__ = "analytic_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    fiscal_year_id = db.Column(db.Integer, db.ForeignKey("fiscal_years.id", ondelete="CASCADE"), nullable=False, unique=True)
    snapshot_json = db.Column(db.Text, nullable=False)
    frozen_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
