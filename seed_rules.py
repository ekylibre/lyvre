"""One-shot seed: import data/rules.yml into the per-instance `rules` table.

Idempotent: if any row already exists in `rules`, the script reports it and
exits 0 without writing.

Usage:
    DATABASE_URL=sqlite:///<tenant>.db python seed_rules.py
    # …or just `python seed_rules.py` to seed the default DATABASE_URL.

Called automatically by app/services/instance_provisioning.py when a new
instance is provisioned via the UI.
"""

import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Rule  # noqa: E402


YAML_PATH = Path(__file__).parent / "data" / "rules.yml"


def _amount_to_cents(value):
    if value is None or value == "":
        return None
    return int(round(float(value) * 100))


def _clean(value):
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def main() -> int:
    app = create_app()
    with app.app_context():
        existing = db.session.query(Rule).count()
        if existing > 0:
            print(f"rules table already populated ({existing} rows) — skipping.")
            return 0

        if not YAML_PATH.exists():
            print(f"Yaml template not found at {YAML_PATH} — nothing to seed.")
            return 0

        with open(YAML_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        entries = data.get("rules") or []

        created = 0
        for i, entry in enumerate(entries, start=1):
            rule = Rule(
                position=i,
                name=_clean(entry.get("name")) or f"Règle {i}",
                label_contains=_clean(entry.get("label_contains")),
                label_regex=_clean(entry.get("label_regex")),
                amount_min_cents=_amount_to_cents(entry.get("amount_min")),
                amount_max_cents=_amount_to_cents(entry.get("amount_max")),
                raw_type=_clean(entry.get("raw_type")),
                entity_name=_clean(entry.get("entity")),
                entity_type=_clean(entry.get("entity_type")),
                category=_clean(entry.get("category")),
                account_code=_clean(entry.get("account")),
                is_active=True,
            )
            db.session.add(rule)
            created += 1

        db.session.commit()
        print(f"Seed terminé : {created} règle(s) importée(s) depuis {YAML_PATH.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
