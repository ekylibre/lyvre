"""Orchestration commune des restaurations Ekylibre (lot RE1) : analyse à blanc et import tout-ou-rien.

Utilisé par `restore_ekylibre.py` (profil `standard`) et `import_ekylibre_sci.py` (profil `sci-chenes-verts`).
Aucun import de l'application au chargement du module : la configuration (méta-base, base de l'instance)
est lue à l'import de `app` et doit être posée avant (variables d'environnement).
"""
import os
import shutil
from pathlib import Path
from types import SimpleNamespace


def analyse(source_path, make_profile):
    """Lecture complète, profil (`make_profile(data)`), période, correspondances et contrôles."""
    from app.services.ekylibre.restore import analyse as shared
    return shared(source_path, make_profile)


def dry_run(source_path, make_profile) -> tuple[str, int]:
    from app.services.ekylibre import report
    data, mapping, results, profile = analyse(source_path, make_profile)
    text = report.render(data, mapping, results, str(source_path), dry_run=True, profile=profile)
    return text, 1 if any(not c.ok and c.blocking for c in results) else 0


def _sqlite_path(url: str) -> Path:
    if not url.startswith("sqlite:////"):
        raise SystemExit("--meta-url : URL SQLite absolue attendue (sqlite:////chemin/meta.db).")
    return Path(url[len("sqlite:///"):])


def _has_associates(data, profile) -> bool:
    if profile.is_sci or data.rows["associates"]:
        return True
    return profile.associates_from_cashes and any(c.get("nature") == "associate_account" for c in data.rows["cashes"])


def run_import(source_path, make_profile, meta_url: str, slug: str, label: str, replace: bool) -> tuple[str, int]:
    """Base construite à part (`<slug>.db.part`), provisionnée pour le référentiel du profil, remplie, contrôlée,
    puis renommée et inscrite dans la méta-base ; rien ne reste en cas d'erreur."""
    meta_path = _sqlite_path(meta_url)
    if not meta_path.exists():
        raise SystemExit(f"Méta-base introuvable : {meta_path}")
    target_dir = meta_path.parent / "tenants"
    target_dir.mkdir(exist_ok=True)
    final = target_dir / f"{slug}.db"
    part = target_dir / f"{slug}.db.part"
    url = f"sqlite:///{part}"
    os.environ["META_DATABASE_URL"] = meta_url
    os.environ["DATABASE_URL"] = url  # avant tout import de l'application (configuration lue à l'import)

    from app.services.ekylibre import report
    from app.services.instance_provisioning import provision_sqlite_database
    data, mapping, results, profile = analyse(source_path, make_profile)
    blocking = [c for c in results if not c.ok and c.blocking]
    if blocking:
        return report.render(data, mapping, results, str(source_path), dry_run=True, profile=profile), 1
    associates = _has_associates(data, profile)

    from app import create_app
    from app.extensions import db
    from app.models import Instance, InstanceMembership
    app = create_app()
    app.instance_path = str(meta_path.parent)  # pièces dans <dossier de la méta>/uploads/<slug>/
    with app.app_context():
        existing = db.session.query(Instance).filter_by(slug=slug).first()
        if (existing is not None or final.exists()) and not replace:
            raise SystemExit(f"L'instance {slug} existe déjà : --replace pour la recréer.")
    if part.exists():
        part.unlink()
    provision_sqlite_database(url, profile.chart)
    try:
        from flask import g
        from app.services.ekylibre import importer
        from app.services.ekylibre.mapping import Chart
        from app.services.ekylibre.reader import open_source
        with app.app_context():
            g.current_instance = SimpleNamespace(slug=slug, label=label, chart=profile.chart, bookkeeping="double",
                                                 has_associates=associates, integrations=None, id=None)
            chart = Chart.from_database()
            mapping = report.plan(data, chart, profile)
            with open_source(source_path) as source:
                ctx = importer.run(data, mapping["accounts"], mapping["entities"], chart, source=source,
                                   attachments_from=profile.attachments_from, profile=profile)
            db.session.commit()
            text = report.render(data, mapping, results, str(source_path), dry_run=False, imported=ctx, profile=profile)
            db.session.remove()
            db.engine.dispose()
    except BaseException:
        part.unlink(missing_ok=True)
        raise

    if final.exists():
        shutil.copy2(final, final.with_suffix(".before-reprise.db"))
        final.unlink()
    part.rename(final)
    with app.app_context():
        instance = db.session.query(Instance).filter_by(slug=slug).first()
        if instance is None:
            instance = Instance(slug=slug, label=label, chart=profile.chart, bookkeeping="double",
                                database_url=f"sqlite:///{final}", has_associates=associates,
                                integrations='{"enabled": [], "dismissed": []}')
            db.session.add(instance)
            db.session.flush()
            source = (db.session.query(Instance).filter_by(slug=profile.copy_access_from).first()
                      if profile.copy_access_from else None)
            if source is not None:
                for member in db.session.query(InstanceMembership).filter_by(instance_id=source.id):
                    db.session.add(InstanceMembership(user_id=member.user_id, instance_id=instance.id, role=member.role))
        else:
            instance.database_url = f"sqlite:///{final}"
        db.session.commit()
    return text, 0
