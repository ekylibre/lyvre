"""Lot F3 : lettrage initial des pièces de Lyvre déjà payées (factures de vente émises, factures
d'achat comptabilisées) dans la base de l'instance (`DATABASE_URL`). Idempotent ; aussi disponible
sur l'écran Compta › Lettrage (administrateur).

Usage : DATABASE_URL=sqlite:////chemin/instance.db .venv/bin/python scripts/lettering_reprise.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.services import lettering  # noqa: E402


def main():
    app = create_app()
    with app.app_context():
        result = lettering.reprise()
        db.session.commit()
        print(f"Ventes : {result['sales']}, achats : {result['purchases']}, lettrages créés : {result['letterings']}")


if __name__ == "__main__":
    main()
