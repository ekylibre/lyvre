from decimal import Decimal
from app.extensions import db
from app.models import BankTransaction


def import_ofx(file_obj, bank_account_id):
    """
    Parse an OFX file and insert new transactions into bank_transactions.
    Returns dict: {imported: int, duplicates: int, errors: list}
    """
    from ofxtools import OFXTree

    parser = OFXTree()
    parser.parse(file_obj)
    ofx = parser.convert()

    imported = 0
    duplicates = 0
    errors = []

    for stmt in ofx.statements:
        for txn in stmt.transactions:
            fitid = txn.fitid
            existing = BankTransaction.query.filter_by(
                bank_account_id=bank_account_id, fitid=fitid
            ).first()
            if existing:
                duplicates += 1
                continue

            try:
                amount_cents = int(Decimal(str(txn.trnamt)) * 100)
                bt = BankTransaction(
                    bank_account_id=bank_account_id,
                    fitid=fitid,
                    transaction_date=txn.dtposted.date(),
                    value_date=txn.dtavail.date() if txn.dtavail else None,
                    amount_cents=amount_cents,
                    label=(txn.memo or txn.name or "").strip(),
                    raw_type=txn.trntype,
                )
                db.session.add(bt)
                imported += 1
            except Exception as e:
                errors.append(f"FITID {fitid}: {e}")

    db.session.commit()
    return {"imported": imported, "duplicates": duplicates, "errors": errors}
