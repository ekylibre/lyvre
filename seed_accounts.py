"""
One-time script to load the Plan Comptable Associatif from JSON into the database.
Usage: flask shell < seed_accounts.py  OR  python seed_accounts.py
"""
import json
from pathlib import Path
from app import create_app
from app.extensions import db
from app.models import Account, Journal

app = create_app()

with app.app_context():
    # Seed plan comptable
    data_path = Path(__file__).parent / "data" / "plan_comptable_asso.json"
    accounts_data = json.loads(data_path.read_text(encoding="utf-8"))

    created = 0
    for entry in accounts_data:
        if Account.query.filter_by(code=entry["code"]).first():
            continue
        account = Account(
            code=entry["code"],
            label=entry["label"],
            account_type=entry["account_type"],
            is_header=entry["is_header"],
        )
        db.session.add(account)
        created += 1

    # Wire parent relationships based on code prefix
    db.session.flush()
    all_accounts = {a.code: a for a in Account.query.all()}
    for account in all_accounts.values():
        if account.parent_id:
            continue
        # Find longest prefix that is a valid account code
        for length in range(len(account.code) - 1, 0, -1):
            parent_code = account.code[:length]
            if parent_code in all_accounts and parent_code != account.code:
                account.parent_id = all_accounts[parent_code].id
                break

    db.session.commit()
    print(f"Plan comptable: {created} comptes créés ({len(all_accounts)} au total).")

    # Seed default journals
    default_journals = [
        ("BQ", "Banque"),
        ("CA", "Caisse"),
        ("VT", "Ventes"),
        ("AC", "Achats"),
        ("OD", "Opérations diverses"),
        ("AN", "À-nouveaux"),
    ]
    j_created = 0
    for code, label in default_journals:
        if not Journal.query.filter_by(code=code).first():
            db.session.add(Journal(code=code, label=label))
            j_created += 1
    db.session.commit()
    print(f"Journaux: {j_created} journaux créés.")
