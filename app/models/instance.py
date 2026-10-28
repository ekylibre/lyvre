import json
from datetime import datetime

from app.extensions import db


class Instance(db.Model):
    __tablename__ = "instances"
    __bind_key__ = "meta"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    label = db.Column(db.String(200), nullable=False)
    database_url = db.Column(db.String(500), nullable=False)
    # Plan comptable de l'instance ("asso", "sci", "societe"). Pilote l'affichage des
    # menus (voir app/menu_config.py).
    chart = db.Column(db.String(20), nullable=False, default="asso", server_default="asso")
    # Mode de tenue (lot D, D19) : "double" (partie double) ou "simple" (recettes et dépenses,
    # associations seulement) ; pilote menus et fonctions comme le plan comptable.
    bookkeeping = db.Column(db.String(10), nullable=False, default="double", server_default="double")
    # Module « Associés » (sociétés) : activé par l'administrateur de l'instance, d'office pour une
    # instance créée au plan SCI ; pilote le menu (lu sans ouvrir la base de l'instance).
    has_associates = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    # Intégrations (interrupteurs, propositions écartées) : {"enabled": [...], "dismissed": [...]} ;
    # NULL tant que l'instance n'a pas été initialisée (external_config.ensure_initialized). Lu
    # sans ouvrir la base de l'instance (menus, session) ; les réglages restent dans cette base.
    integrations = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def _integrations(self) -> dict:
        try:
            value = json.loads(self.integrations or "{}")
        except ValueError:
            value = {}
        return value if isinstance(value, dict) else {}

    def _set_integrations(self, enabled, dismissed, scopes=None) -> None:
        value = {"enabled": sorted(enabled), "dismissed": sorted(dismissed)}
        scopes = self._integrations().get("scopes") if scopes is None else scopes
        if scopes:
            value["scopes"] = {service: sorted(items) for service, items in scopes.items()}
        self.integrations = json.dumps(value)

    def integration_scopes(self, service: str) -> set[str] | None:
        """Périmètre enregistré d'une intégration (Qonto : relevés, achats, ventes) ; None : défaut."""
        scopes = (self._integrations().get("scopes") or {}).get(service)
        return None if scopes is None else set(scopes)

    def set_integration_scopes(self, service: str, scopes) -> None:
        current = dict(self._integrations().get("scopes") or {})
        current[service] = sorted(set(scopes))
        self._set_integrations(self.enabled_integrations(), self.dismissed_integrations(), current)

    def enabled_integrations(self) -> set[str]:
        return set(self._integrations().get("enabled") or [])

    def dismissed_integrations(self) -> set[str]:
        return set(self._integrations().get("dismissed") or [])

    def set_integration(self, service: str, enabled: bool) -> None:
        current = self.enabled_integrations()
        current = current | {service} if enabled else current - {service}
        self._set_integrations(current, self.dismissed_integrations())

    def dismiss_integration(self, service: str) -> None:
        self._set_integrations(self.enabled_integrations(), self.dismissed_integrations() | {service})

    def __repr__(self):
        return f"<Instance {self.slug}>"
