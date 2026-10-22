"""Serveur Flask des tests de bout en bout (Playwright, frontend/e2e/).

Bases SQLite et dossier d'instance jetables (jamais les vraies données) :
méta-base avec l'utilisateur et les instances de frontend/e2e/fixtures.json,
une base tenant vide par instance. Les fichiers du front doivent être construits
(`npm --prefix frontend run build`).
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

with open(os.path.join(ROOT, "frontend", "e2e", "fixtures.json"), encoding="utf-8") as fh:
    FIXTURES = json.load(fh)

TMPDIR = tempfile.mkdtemp(prefix="compta-asso-e2e-")
os.environ["META_DATABASE_URL"] = f"sqlite:///{os.path.join(TMPDIR, 'meta.db')}"
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(TMPDIR, 'default.db')}"
os.environ.pop("VITE_DEV_SERVER", None)

from sqlalchemy import create_engine  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Instance, User  # noqa: E402


def seed(app):
    with app.app_context():
        db.create_all()
        user = User(email=FIXTURES["user"]["email"], full_name="Testeur E2E", is_admin=True)
        user.set_password(FIXTURES["user"]["password"])
        db.session.add(user)
        for spec in FIXTURES["instances"]:
            url = f"sqlite:///{os.path.join(TMPDIR, spec['slug'] + '.db')}"
            engine = create_engine(url)
            db.metadata.create_all(engine)  # tables tenant (la méta-base a ses propres métadonnées)
            engine.dispose()
            db.session.add(Instance(slug=spec["slug"], label=spec["label"], chart=spec["chart"],
                                    database_url=url))
        db.session.commit()


def main():
    app = create_app("development")
    app.instance_path = TMPDIR
    seed(app)
    print(f"[e2e] base jetable : {TMPDIR}", flush=True)
    app.run(host="127.0.0.1", port=FIXTURES["port"], debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
