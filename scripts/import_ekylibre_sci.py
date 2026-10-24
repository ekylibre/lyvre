"""Reprise de la SCI Chênes Verts depuis un export de tenant Ekylibre (voir
`claudedocs/design_import_ekylibre_sci.md`).

Analyse à blanc (rien n'est écrit) :
  .venv/bin/python scripts/import_ekylibre_sci.py ARCHIVE.zip --dry-run [--report rapport.md]

Import (base neuve, tout-ou-rien) :
  .venv/bin/python scripts/import_ekylibre_sci.py ARCHIVE.zip --meta-url sqlite:////chemin/meta.db \\
      [--slug sci-chenes-verts] [--label "SCI Chênes Verts"] [--replace] [--report rapport.md]

La base est construite dans `<dossier de la méta-base>/tenants/<slug>.db.part`, provisionnée comme
une instance neuve (plan SCI), remplie par les services de Lyvre, contrôlée (balance = Ekylibre,
corrections comprises), puis renommée et inscrite dans la méta-base ; en cas d'erreur, rien ne reste.
`--meta-url` est obligatoire pour l'import : jamais la méta-base par défaut sans le vouloir.
Aucun accès réseau, aucun identifiant Qonto.
"""
import argparse
import os
import shutil
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def analyse(source_path, start: date, until: date, chart=None):
    from app.services.ekylibre import checks, report
    from app.services.ekylibre.data import EkyData
    from app.services.ekylibre.mapping import Chart
    from app.services.ekylibre.reader import open_source
    with open_source(source_path) as source:
        data = EkyData.load(source, start, until)
    results = checks.run(data)
    mapping = report.plan(data, chart or Chart.from_file())
    return data, mapping, results


def _sqlite_path(url: str) -> Path:
    if not url.startswith("sqlite:////"):
        raise SystemExit("--meta-url : URL SQLite absolue attendue (sqlite:////chemin/meta.db).")
    return Path(url[len("sqlite:///"):])


def run_import(args, start: date, until: date) -> tuple[str, int]:
    meta_path = _sqlite_path(args.meta_url)
    if not meta_path.exists():
        raise SystemExit(f"Méta-base introuvable : {meta_path}")
    target_dir = meta_path.parent / "tenants"
    target_dir.mkdir(exist_ok=True)
    final = target_dir / f"{args.slug}.db"
    part = target_dir / f"{args.slug}.db.part"
    url = f"sqlite:///{part}"
    os.environ["META_DATABASE_URL"] = args.meta_url
    os.environ["DATABASE_URL"] = url  # avant tout import de l'application (configuration lue à l'import)

    from app.services.ekylibre import report
    from app.services.instance_provisioning import provision_sqlite_database
    data, mapping, results = analyse(args.source, start, until)
    blocking = [c for c in results if not c.ok and c.blocking]
    if blocking:
        return report.render(data, mapping, results, str(args.source), dry_run=True), 1

    from app import create_app
    from app.extensions import db
    from app.models import Instance, InstanceMembership
    app = create_app()
    with app.app_context():
        existing = db.session.query(Instance).filter_by(slug=args.slug).first()
        if (existing is not None or final.exists()) and not args.replace:
            raise SystemExit(f"L'instance {args.slug} existe déjà : --replace pour la recréer.")
    if part.exists():
        part.unlink()
    provision_sqlite_database(url, "sci")
    try:
        from flask import g
        from app.services.ekylibre import importer
        from app.services.ekylibre.mapping import Chart
        with app.app_context():
            g.current_instance = SimpleNamespace(slug=args.slug, chart="sci", bookkeeping="double", has_associates=True,
                                                 integrations=None, id=None)
            chart = Chart.from_database()
            mapping = report.plan(data, chart)
            ctx = importer.run(data, mapping["accounts"], mapping["entities"], chart)
            db.session.commit()
            text = report.render(data, mapping, results, str(args.source), dry_run=False, imported=ctx)
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
        instance = db.session.query(Instance).filter_by(slug=args.slug).first()
        if instance is None:
            instance = Instance(slug=args.slug, label=args.label, chart="sci", bookkeeping="double",
                                database_url=f"sqlite:///{final}", has_associates=True,
                                integrations='{"enabled": [], "dismissed": []}')
            db.session.add(instance)
            db.session.flush()
            source = db.session.query(Instance).filter_by(slug=args.copy_access_from).first()
            if source is not None:
                for member in db.session.query(InstanceMembership).filter_by(instance_id=source.id):
                    db.session.add(InstanceMembership(user_id=member.user_id, instance_id=instance.id, role=member.role))
        else:
            instance.database_url = f"sqlite:///{final}"
        db.session.commit()
    return text, 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", help="archive .zip de l'export Ekylibre, ou dossier extrait")
    parser.add_argument("--start", default="2025-01-01", help="début de la reprise (AAAA-MM-JJ)")
    parser.add_argument("--until", default="2026-06-30", help="date limite incluse (AAAA-MM-JJ)")
    parser.add_argument("--dry-run", action="store_true", help="analyse à blanc : rapport seulement")
    parser.add_argument("--meta-url", help="méta-base visée (sqlite:////chemin/meta.db), obligatoire pour l'import")
    parser.add_argument("--slug", default="sci-chenes-verts")
    parser.add_argument("--label", default="SCI Chênes Verts")
    parser.add_argument("--copy-access-from", default="chenes-verts", help="instance dont les accès sont repris")
    parser.add_argument("--replace", action="store_true", help="recrée l'instance si elle existe (sauvegarde gardée)")
    parser.add_argument("--report", help="fichier du rapport Markdown")
    args = parser.parse_args(argv)
    start, until = date.fromisoformat(args.start), date.fromisoformat(args.until)
    if args.dry_run:
        from app.services.ekylibre import report
        data, mapping, results = analyse(args.source, start, until)
        text = report.render(data, mapping, results, str(args.source), dry_run=True)
        code = 1 if any(not c.ok and c.blocking for c in results) else 0
    else:
        if not args.meta_url:
            parser.error("--meta-url est obligatoire pour l'import (ou --dry-run pour l'analyse à blanc).")
        text, code = run_import(args, start, until)
    if args.report:
        Path(args.report).write_text(text, encoding="utf-8")
        print(f"Rapport : {args.report}")
    print(text.split("## Journaux")[0])
    return code


if __name__ == "__main__":
    sys.exit(main())
