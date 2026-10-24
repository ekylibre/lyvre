"""Import d'écritures depuis un tableur (lot F6) : CSV (séparateur détecté) ou XLSX (première feuille).

Colonnes associées une fois (profil mémorisé, `import_profiles`) : date, journal, pièce, compte,
libellé, débit, crédit (ou montant signé). Les lignes d'une même pièce (sinon même date et même
libellé) forment une écriture ; mêmes contrôles et même tout-ou-rien que l'import FEC ; écritures en
brouillard (source `SHEET_IMPORT`) dans l'exercice ouvert de leur date. Comptes : mêmes
correspondances que le FEC (`fec_import.plan_accounts`).
"""
import csv
import io
import json
import re
import unicodedata
from datetime import date, datetime, timedelta

from app.extensions import db
from app.models import FiscalYear, ImportProfile, Journal
from app.models.journal_entry import SOURCE_SHEET_IMPORT
from app.services.fec_import import ImportError_, amount, apply_plan, plan_accounts

FIELDS = ("date", "journal", "piece", "account", "account_label", "label", "debit", "credit", "amount")
FIELD_LABELS = {"date": "Date", "journal": "Journal", "piece": "Pièce", "account": "Compte", "account_label": "Libellé du compte",
                "label": "Libellé", "debit": "Débit", "credit": "Crédit", "amount": "Montant (signé)"}
GUESS = {"date": ("date", "dateecriture", "ecrituredate"), "journal": ("journal", "codejournal", "journalcode"),
         "piece": ("piece", "pieceref", "numero", "numeropiece", "ecriturenum", "reference", "ref"),
         "account": ("compte", "comptenum", "numerodecompte", "account"), "account_label": ("libelleducompte", "comptelib"),
         "label": ("libelle", "ecriturelib", "label", "designation"), "debit": ("debit",), "credit": ("credit",),
         "amount": ("montant", "amount")}
MAX_SIZE = 10 * 1024 * 1024


def _plain(text) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower())


def read(content: bytes, filename: str) -> tuple[list[str], list[list[str]]]:
    """En-têtes et lignes (texte) du fichier."""
    if len(content) > MAX_SIZE:
        raise ImportError_("Fichier trop volumineux (10 Mo au plus).")
    if (filename or "").lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        try:
            sheet = load_workbook(io.BytesIO(content), read_only=True, data_only=True).worksheets[0]
        except Exception as exc:  # noqa: BLE001 — fichier illisible : message à l'écran
            raise ImportError_(f"Classeur illisible : {exc}") from None
        rows = [["" if v is None else (v.date().isoformat() if isinstance(v, datetime) else
                                        v.isoformat() if isinstance(v, date) else str(v)) for v in row]
                for row in sheet.iter_rows(values_only=True)]
    else:
        from app.services.fec_import import decode
        text = decode(content)
        first = text.splitlines()[0] if text.strip() else ""
        delimiter = max((";", ",", "\t"), key=first.count)
        rows = [r for r in csv.reader(io.StringIO(text), delimiter=delimiter)]
    rows = [[c.strip() for c in r] for r in rows if any(str(c).strip() for c in r)]
    if not rows:
        raise ImportError_("Fichier vide.")
    return rows[0], rows[1:]


def guess_mapping(headers: list[str]) -> dict[str, str]:
    plain = {_plain(h): h for h in headers}
    mapping = {}
    for name, candidates in GUESS.items():
        found = next((plain[c] for c in candidates if c in plain), None)
        if found:
            mapping[name] = found
    return mapping


def _day(value: str) -> date | None:
    value = (value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%Y%m%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value[:10] if fmt == "%Y-%m-%d" else value, fmt).date()
        except ValueError:
            continue
    if re.fullmatch(r"\d{5}(\.0)?", value):  # date Excel non formatée
        return date(1899, 12, 30) + timedelta(days=int(float(value)))
    return None


def build(headers, rows, mapping: dict) -> tuple[list[dict], list[str]]:
    """Écritures (`{key, date, journal, piece, lines}`) et anomalies."""
    missing = [FIELD_LABELS[f] for f in ("date", "account") if not mapping.get(f)]
    if not (mapping.get("amount") or (mapping.get("debit") and mapping.get("credit"))):
        missing.append("Débit et Crédit (ou Montant)")
    if missing:
        raise ImportError_("Colonnes à associer : " + ", ".join(missing) + ".")
    index = {h: i for i, h in enumerate(headers)}

    def get(row, name):
        column = mapping.get(name)
        i = index.get(column) if column else None
        return row[i].strip() if i is not None and i < len(row) else ""

    entries, problems, by_key = [], [], {}
    for n, row in enumerate(rows, start=2):
        day = _day(get(row, "date"))
        code = get(row, "account").split(".")[0].strip()
        try:
            if mapping.get("amount"):
                value = amount(get(row, "amount"))
                debit, credit = max(value, 0), max(-value, 0)
            else:
                debit, credit = amount(get(row, "debit")), amount(get(row, "credit"))
        except ValueError:
            problems.append(f"Ligne {n} : montant illisible.")
            continue
        if day is None or not code:
            problems.append(f"Ligne {n} : date ou compte manquant.")
            continue
        if not debit and not credit:
            continue
        piece, label = get(row, "piece"), get(row, "label")
        key = piece or f"{day.isoformat()}|{label}"
        if key not in by_key:
            by_key[key] = {"key": key, "date": day, "journal": (get(row, "journal") or "OD")[:10], "piece": piece,
                           "label": label, "lines": []}
            entries.append(by_key[key])
        by_key[key]["lines"].append({"account": code, "account_label": get(row, "account_label"), "label": label,
                                     "debit": debit, "credit": credit})
    for entry in entries:
        balance = sum(l["debit"] - l["credit"] for l in entry["lines"])
        if balance:
            problems.append(f"Pièce {entry['piece'] or entry['key']} déséquilibrée ({balance / 100:.2f} €).")
        fy = FiscalYear.query.filter(FiscalYear.start_date <= entry["date"], FiscalYear.end_date >= entry["date"]).first()
        if fy is None or fy.closed:
            problems.append(f"Pièce {entry['piece'] or entry['key']} : aucun exercice ouvert au {entry['date']:%d/%m/%Y}.")
    return entries, problems


def _sources(entries) -> dict[str, dict]:
    sources = {}
    for entry in entries:
        for line in entry["lines"]:
            sources.setdefault(line["account"], {"code": line["account"], "label": line["account_label"] or line["account"]})
    return sources


def analyze(content: bytes, filename: str, mapping: dict | None = None, overrides: dict | None = None) -> dict:
    headers, rows = read(content, filename)
    mapping = mapping or guess_mapping(headers)
    result = {"headers": headers, "mapping": mapping, "sample": rows[:5], "rows": len(rows),
              "fields": [{"value": f, "label": FIELD_LABELS[f]} for f in FIELDS]}
    try:
        entries, problems = build(headers, rows, mapping)
    except ImportError_ as exc:
        return {**result, "entries": 0, "problems": [str(exc)], "accounts": []}
    plan = plan_accounts(_sources(entries), overrides)
    db.session.rollback()
    return {**result, "entries": len(entries), "lines": sum(len(e["lines"]) for e in entries),
            "problems": problems[:50], "accounts": plan, "to_create": sum(1 for r in plan if r["action"] == "create")}


def run(content: bytes, filename: str, mapping: dict, overrides: dict | None = None, profile_name: str | None = None,
        user_id=None) -> dict:
    """Importe les écritures en brouillard (tout-ou-rien, commit)."""
    from app.services.ledger import post_entry
    headers, rows = read(content, filename)
    entries, problems = build(headers, rows, mapping)
    if problems:
        raise ImportError_(f"{len(problems)} anomalie(s) : rien n'est importé.", problems)
    if not entries:
        raise ImportError_("Aucune écriture à importer.")
    try:
        accounts = apply_plan(plan_accounts(_sources(entries), overrides))
        journals = {}
        count = 0
        for entry in entries:
            code = entry["journal"]
            if code not in journals:
                journals[code] = Journal.query.filter_by(code=code).first()
                if journals[code] is None:
                    journals[code] = Journal(code=code, label=code)
                    db.session.add(journals[code])
                    db.session.flush()
            fy = FiscalYear.query.filter(FiscalYear.start_date <= entry["date"], FiscalYear.end_date >= entry["date"]).first()
            post_entry(fy.id, journals[code].id, entry["date"], (entry["label"] or entry["piece"] or "Écriture importée")[:500],
                       [{"account_id": accounts[l["account"]].id, "label": (l["label"] or "")[:300], "debit_cents": l["debit"],
                         "credit_cents": l["credit"]} for l in entry["lines"]],
                       source=SOURCE_SHEET_IMPORT, source_ref=(entry["piece"] or None) and f"SHEET:{entry['piece']}"[:200],
                       commit=False)
            count += 1
        if profile_name:
            save_profile(profile_name, "xlsx" if filename.lower().endswith((".xlsx", ".xlsm")) else "csv", mapping)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return {"entries": count}


def save_profile(name: str, kind: str, mapping: dict) -> ImportProfile:
    profile = ImportProfile.query.filter_by(name=name.strip()[:100]).first()
    if profile is None:
        profile = ImportProfile(name=name.strip()[:100], kind=kind, columns_json="{}")
        db.session.add(profile)
    profile.kind, profile.columns_json = kind, json.dumps(mapping, ensure_ascii=False)
    return profile


def profiles() -> list[dict]:
    return [{"id": p.id, "name": p.name, "kind": p.kind, "mapping": json.loads(p.columns_json)}
            for p in ImportProfile.query.order_by(ImportProfile.name)]
