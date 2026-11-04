"""Chargement d'une exploitation fictive du jeu d'essai (lot AG1.f) dans la base de l'instance courante :
forme et régimes (profile.json), puis
- FEC (A, B, C) : premier exercice par l'import FEC de Lyvre (historique, clôture provisoire), à-nouveaux de
  l'exercice suivant par l'assistant de clôture, écritures des exercices suivants dans ces exercices ;
- opérations (D) : recettes et dépenses du mode simple par catégorie.

À appeler dans un contexte d'application dont l'instance courante est au plan « agri » (tests, serveur E2E) :

    from scripts.agri_fixtures.load import load
    load(Path("tests/fixtures/agri/A_earl_porcs_rs"))
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "agri"


def _profile(directory: Path, profile: dict) -> None:
    from app.extensions import db
    from app.models import TaxProfile
    from app.services import organization

    org = organization.get()
    org.name = profile["label"]
    org.legal_form_code = profile["legal_form_code"]
    start = date.fromisoformat(profile["fiscal_years"][0]["start"])
    db.session.add(TaxProfile(kind="income_tax", value=profile["income_tax"], start_date=start))
    if profile.get("ba_regime"):
        db.session.add(TaxProfile(kind="ba_regime", value=profile["ba_regime"], start_date=start))
    if profile.get("vat_regime"):
        db.session.add(TaxProfile(kind="vat_regime", value=profile["vat_regime"], start_date=start))
    db.session.commit()


def _post_following(directory: Path, item: dict, fy) -> int:
    """Écritures d'un exercice suivant (déjà ouvert par les à-nouveaux) : mêmes correspondances que l'import."""
    from app.extensions import db
    from app.models.journal_entry import SOURCE_FEC_IMPORT
    from app.services import fec_import
    from app.services.ledger import post_entry

    entries, problems = fec_import.parse((directory / item["file"]).read_bytes())
    if problems:
        raise ValueError(f"{item['file']} : {problems[:3]}")
    journals = fec_import._journals(entries)
    accounts = fec_import.apply_plan(fec_import.plan_accounts(fec_import._sources(entries)))
    for entry in sorted(entries, key=lambda e: (e.day, e.journal, e.number)):
        rows = [{"account_id": accounts[l.key].id, "label": l.label[:300], "debit_cents": l.debit,
                 "credit_cents": l.credit} for l in entry.lines]
        post_entry(fy.id, journals[entry.journal[:10]].id, entry.day, entry.lines[0].label[:500], rows,
                   source=SOURCE_FEC_IMPORT, source_ref=f"{entry.journal}{entry.number}", commit=False)
    db.session.commit()
    return len(entries)


def _load_fec(directory: Path, profile: dict) -> dict:
    from app.models import FiscalYear
    from app.services import closing, fec_import

    loaded = {}
    previous = None
    for item in profile["fiscal_years"]:
        start, end = date.fromisoformat(item["start"]), date.fromisoformat(item["end"])
        if previous is None:
            result = fec_import.import_history((directory / item["file"]).read_bytes(), item["file"], start, end)
            previous = FiscalYear.query.get(result["fiscal_year_id"])
            loaded[item["file"]] = result["entries"]
        else:
            closing.generate_opening(previous, create_next=True)
            fy = FiscalYear.query.filter(FiscalYear.start_date == start).one()
            loaded[item["file"]] = _post_following(directory, item, fy)
            previous = fy
    return loaded


def _load_operations(directory: Path, profile: dict) -> dict:
    from app.extensions import db
    from app.models import Account, BankAccount, FiscalYear, SimpleCategory
    from app.services import simple_categories, simple_operations

    for item in profile["fiscal_years"]:
        db.session.add(FiscalYear(label=item["start"][:4], start_date=date.fromisoformat(item["start"]),
                                  end_date=date.fromisoformat(item["end"])))
    bank = Account.query.filter_by(code="512").first()
    account = BankAccount(label="Compte courant", account_id=bank.id)
    db.session.add(account)
    db.session.commit()
    simple_categories.ensure_defaults()
    categories = {c.code: c.id for c in SimpleCategory.query}
    ops = json.loads((directory / "operations.json").read_text("utf-8"))
    for op in ops:
        simple_operations.create({"date": op["date"], "label": op["label"], "amount_cents": op["amount_cents"],
                                  "category_id": categories[op["category"]], "bank_account_id": account.id})
    return {"operations": len(ops)}


def load(directory: Path) -> dict:
    """Charge l'exploitation du dossier ``directory`` ; renvoie le nombre d'écritures par fichier."""
    profile = json.loads((directory / "profile.json").read_text("utf-8"))
    _profile(directory, profile)
    if (directory / "operations.json").exists():
        return _load_operations(directory, profile)
    return _load_fec(directory, profile)
