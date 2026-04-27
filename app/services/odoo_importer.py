import io
from decimal import Decimal, InvalidOperation
from datetime import date
import pandas as pd
from app.extensions import db
from app.models import OdooImportLine

# Expected Odoo CSV column names → internal field mapping
COLUMN_MAP = {
    "name": "invoice_number",
    "invoice_date": "invoice_date",
    "partner_id/name": "partner_name",
    "product_id/name": "product_name",
    "price_subtotal": "amount_ht",
    "price_total": "amount_ttc",
    "account_id/code": "account_code",
}


def _parse_amount(val):
    try:
        return int(Decimal(str(val).replace(",", ".").replace(" ", "")) * 100)
    except (InvalidOperation, ValueError):
        return 0


def _parse_date(val):
    if pd.isna(val):
        return None
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return None


def import_odoo_csv(file_obj, batch_name):
    """
    Parse an Odoo invoice lines CSV and insert into odoo_import_lines.
    Returns dict: {imported: int, errors: list, preview: list[dict]}
    """
    try:
        df = pd.read_csv(file_obj, encoding="utf-8", dtype=str)
    except UnicodeDecodeError:
        file_obj.seek(0)
        df = pd.read_csv(file_obj, encoding="latin-1", dtype=str)

    df.columns = [c.strip() for c in df.columns]

    # Build reverse map from actual columns
    col_remap = {}
    for src, dst in COLUMN_MAP.items():
        if src in df.columns:
            col_remap[src] = dst

    df = df.rename(columns=col_remap)

    imported = 0
    errors = []
    preview = []

    for i, row in df.iterrows():
        try:
            amount_ht_cents = _parse_amount(row.get("amount_ht", 0))
            amount_ttc_cents = _parse_amount(row.get("amount_ttc", 0))
            tax_cents = amount_ttc_cents - amount_ht_cents

            line = OdooImportLine(
                import_batch=batch_name,
                invoice_number=str(row.get("invoice_number", "") or "").strip(),
                invoice_date=_parse_date(row.get("invoice_date")),
                partner_name=str(row.get("partner_name", "") or "").strip(),
                product_name=str(row.get("product_name", "") or "").strip(),
                amount_ht_cents=amount_ht_cents,
                tax_amount_cents=tax_cents,
                amount_ttc_cents=amount_ttc_cents,
                account_code=str(row.get("account_code", "") or "").strip(),
            )
            db.session.add(line)
            imported += 1

            if len(preview) < 5:
                preview.append({
                    "invoice_number": line.invoice_number,
                    "invoice_date": line.invoice_date,
                    "partner_name": line.partner_name,
                    "amount_ttc_cents": line.amount_ttc_cents,
                    "account_code": line.account_code,
                })
        except Exception as e:
            errors.append(f"Ligne {i + 2}: {e}")

    db.session.commit()
    return {"imported": imported, "errors": errors, "preview": preview, "batch": batch_name}
