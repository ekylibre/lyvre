"""Applique les migrations Alembic à la base de chaque instance déclarée dans la base méta.

`flask db upgrade` seul ne migre que la base par défaut (`DATABASE_URL`) : une autre instance (la SCI
à côté de Seconde Nature) resterait à l'ancienne version, et ses écrans tomberaient en erreur dès
qu'un modèle gagne une colonne. Lancé par l'entrypoint à chaque démarrage, après `seed_meta.py` ;
idempotent (une base à jour n'est pas touchée).

Un échec est signalé et n'empêche ni les autres instances ni le démarrage (code de sortie 0) :
l'instance concernée reste en erreur jusqu'à correction, les autres fonctionnent.
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def instance_urls() -> list[tuple[str, str]]:
    """(slug, database_url) de toutes les instances (la base par défaut comprise : sans effet si à jour)."""
    from app import create_app
    from app.extensions import db
    from app.models import Instance

    with create_app().app_context():
        return [(i.slug, i.database_url) for i in db.session.query(Instance).order_by(Instance.id) if i.database_url]


def upgrade(url: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": url, "FLASK_APP": os.environ.get("FLASK_APP", "run.py")}
    return subprocess.run([sys.executable, "-m", "flask", "db", "upgrade"], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=600)


def main() -> int:
    failures = 0
    for slug, url in instance_urls():
        result = upgrade(url)
        lines = [line for line in (result.stdout + result.stderr).splitlines()
                 if "Running upgrade" in line or line.startswith("[") or "Error" in line]
        if result.returncode == 0:
            print(f"[migrate_instances] {slug} : " + ("à jour" if not lines else f"{len(lines)} étape(s)"))
            for line in lines:
                print(f"[migrate_instances]   {line.split('] ')[-1]}")
        else:
            failures += 1
            print(f"[migrate_instances] {slug} : ÉCHEC de la migration\n{result.stderr[-2000:]}", file=sys.stderr)
    if failures:
        print(f"[migrate_instances] {failures} instance(s) non migrée(s) : voir ci-dessus.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
