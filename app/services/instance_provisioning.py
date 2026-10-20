"""Create a fresh tenant database for a new Instance.

Strategy: run `flask db upgrade` + `seed_accounts.py` as subprocesses with
DATABASE_URL pointing at the new database. Subprocess isolation guarantees
the running app's Flask-Migrate state is not disturbed.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,48}[a-z0-9]$")

# Available charts of accounts: key -> human label. Keys must match seed_accounts.py.
CHARTS = {
    "asso": "Association (loi 1901)",
    "sci": "SCI (société civile immobilière)",
}
DEFAULT_CHART = "asso"


class ProvisioningError(Exception):
    pass


def validate_slug(slug: str) -> str:
    slug = (slug or "").strip().lower()
    if not SLUG_RE.match(slug):
        raise ProvisioningError(
            "Slug invalide. Lettres minuscules, chiffres et tirets uniquement "
            "(2 à 50 caractères, sans tiret en début/fin)."
        )
    return slug


def build_sqlite_url(slug: str) -> str:
    """Return a SQLite URL pointing at instance/tenants/<slug>.db."""
    return f"sqlite:///tenants/{slug}.db"


def database_file_for_url(database_url: str) -> Path | None:
    """Return the absolute filesystem path of a SQLite URL, or None for non-SQLite."""
    if not database_url.startswith("sqlite:///"):
        return None
    raw = database_url[len("sqlite:///"):]
    path = Path(raw)
    if not path.is_absolute():
        # Flask-SQLAlchemy resolves relative SQLite paths against the instance folder.
        path = BASE_DIR / "instance" / path
    return path


def _run(cmd: list[str], database_url: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["FLASK_APP"] = "run.py"
    result = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise ProvisioningError(
            f"Command failed ({' '.join(cmd)}):\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def validate_chart(chart: str) -> str:
    chart = (chart or DEFAULT_CHART).strip().lower()
    if chart not in CHARTS:
        raise ProvisioningError(
            f"Plan comptable invalide. Choix : {', '.join(CHARTS)}."
        )
    return chart


def provision_sqlite_database(database_url: str, chart: str = DEFAULT_CHART) -> None:
    """Create the SQLite file (if absent), apply migrations, seed accounts.

    ``chart`` selects the plan comptable to load ("asso" or "sci").
    """
    chart = validate_chart(chart)
    path = database_file_for_url(database_url)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 0:
            raise ProvisioningError(
                f"Le fichier {path} existe déjà — refus de l'écraser."
            )

    _run([sys.executable, "-m", "flask", "db", "upgrade"], database_url)
    _run([sys.executable, "seed_accounts.py", chart], database_url)
    _run([sys.executable, "seed_rules.py"], database_url)
