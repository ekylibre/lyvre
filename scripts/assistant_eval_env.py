"""Environnement jetable du jeu d'évaluation de l'assistant (lot AG9b.d), hors de la base locale :

    python scripts/assistant_eval_env.py <dossier>

Crée dans <dossier> une méta-base et l'instance agricole « essai-agri » : exploitation fictive A du jeu d'essai
(tests/fixtures/agri/A_earl_porcs_rs), exercice 2024-2025 ouvert à la saisie, un associé exploitant fictif en assiette
MSA annuelle, intégration « Assistant Claude » activée. Puis, avec la clé de l'API dans l'environnement :

    META_DATABASE_URL=sqlite:///<dossier>/meta.db DATABASE_URL=sqlite:///<dossier>/essai-agri.db \\
        python scripts/run_assistant_evals.py --instance essai-agri [--repeat 3]
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    folder = Path(sys.argv[1]).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    tenant = f"sqlite:///{folder / 'essai-agri.db'}"
    os.environ["META_DATABASE_URL"] = f"sqlite:///{folder / 'meta.db'}"
    os.environ["DATABASE_URL"] = tenant
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    from app import create_app
    from app.extensions import db
    app = create_app()
    with app.app_context():
        from app.models import Associate, FiscalYear, Instance, JournalEntry, MsaPerson
        from app.services import associates, instance_provisioning, msa
        from app.services.agenda_summary import _select
        db.create_all(bind_key="meta")
        if Instance.query.filter_by(slug="essai-agri").first() is None:
            instance_provisioning.provision_sqlite_database(tenant, "agri")
            db.session.add(Instance(slug="essai-agri", label="Essai agricole (fictif)", database_url=tenant, chart="agri",
                                    bookkeeping="double", integrations='{"enabled": ["assistant"], "dismissed": []}'))
            db.session.commit()
        with app.test_request_context():
            _select(Instance.query.filter_by(slug="essai-agri").one())
            if JournalEntry.query.count() == 0:
                from scripts.agri_fixtures.load import load
                load(ROOT / "tests" / "fixtures" / "agri" / "A_earl_porcs_rs")
                db.session.commit()
            for fy in FiscalYear.query:
                fy.status = "open"
            db.session.commit()
            if Associate.query.count() == 0:
                associates.create({"new_name": "Camille Essai (fictif)", "is_operator": True, "profit_share": "100"})
            msa.people(FiscalYear.query.order_by(FiscalYear.end_date.desc()).first())
            for person in MsaPerson.query:
                person.base_option, person.option_since = "annual", date(2024, 1, 1)
            db.session.commit()
            print(f"Instance essai-agri prête : {JournalEntry.query.count()} écritures fictives, dans {folder}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
