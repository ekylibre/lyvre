"""Constat avant la mise en place des interrupteurs d'intégration (lecture seule).

Pour chaque instance : intégrations de sa structure, celles qui seront activées à son
initialisation (réglages requis enregistrés dans sa base, ancien interrupteur non désactivé), et
les réglages que le .env fournit aujourd'hui sans être enregistrés dans sa base — à saisir dans
Configuration › Intégrations avant la mise en production (hors développement, le .env est ignoré).

N'écrit rien, n'affiche jamais une valeur (seulement des noms de clés). Les bases sont celles de
META_DATABASE_URL et des instances qu'elle référence ; les variables du .env sont lues comme par
run.py (ou celles du conteneur, `env_file`).

Usage : .venv/bin/python scripts/integrations_report.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402
from flask import g  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import ExternalConnection, Instance, IntegrationState  # noqa: E402
from app.services import external_config  # noqa: E402
from app.tenant import get_tenant_engine  # noqa: E402


def _report(inst: Instance) -> list[str]:
    lines = [f"{inst.slug} ({inst.chart}) — interrupteurs "
             + ("non initialisés" if inst.integrations is None else f"déjà initialisés : {sorted(inst.enabled_integrations())}")]
    g.current_instance, g.tenant_engine = inst, get_tenant_engine(inst)
    try:
        stored = {(r.service, r.key) for r in db.session.query(ExternalConnection).all() if r.value}
        states = {s.service: s.enabled for s in db.session.query(IntegrationState).all()}
    finally:
        db.session.rollback()
        g.current_instance = g.tenant_engine = None
    for service in external_config.applicable(inst.chart):
        required = external_config.SERVICE_REQUIRED_KEYS[service]
        in_db = all((service, k) in stored for k in required)
        would_enable = in_db and states.get(service, True)
        # Variables réellement définies (pas les valeurs par défaut de app/config.py).
        from_env = [k for k in external_config.SERVICE_KEYS[service]
                    if (service, k) not in stored and os.environ.get(external_config.ENV_FALLBACK.get((service, k), ""))]
        status = "activée" if would_enable else ("désactivée (ancien interrupteur)" if in_db else "désactivée")
        line = f"  - {external_config.SERVICE_LABELS[service]} : {status}"
        if from_env:
            line += f" ; fournies par le .env, absentes de la base : {', '.join(from_env)}"
        lines.append(line)
    return lines


def main():
    load_dotenv()
    app = create_app("production")  # repli .env coupé, comme en production
    with app.app_context():
        for inst in db.session.query(Instance).order_by(Instance.slug).all():
            try:
                print("\n".join(_report(inst)))
            except Exception as exc:  # noqa: BLE001 — une base illisible ne bloque pas le constat
                print(f"{inst.slug} : base illisible ({type(exc).__name__})")


if __name__ == "__main__":
    main()
