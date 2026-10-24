"""Reprise d'historique par import d'un FEC (lot F6).

- **Lecture** : séparateur tabulation ou barre verticale, encodage UTF-8 / ISO-8859-15 / Windows-1252,
  18 colonnes (montants `Debit` / `Credit`, ou `Montant` / `Sens`), dates AAAAMMJJ ; écritures
  regroupées par (`JournalCode`, `EcritureNum`) ; contrôles : équilibre, dates.
- **Correspondances** (`plan_accounts`) : compte existant de même code, correspondance mémorisée
  (`account_mappings`), sinon création (rattaché au compte de regroupement le plus proche) ; comptes
  auxiliaires (`CompAuxNum`) : sous-compte du tiers (401NNN, 411NNN…) et fiche du tiers, retrouvés
  ou créés ; l'utilisateur peut faire correspondre un compte du fichier à un compte existant.
- **Import tout-ou-rien**, deux modes :
  - `history` : l'exercice du fichier est créé, ses écritures importées (source `FEC_IMPORT`,
    `source_ref` = numéro d'origine), validées (lot `import`), les lettrages repris (`EcritureLet`),
    puis l'exercice est clôturé provisoirement et verrouillé ; les à-nouveaux de l'exercice suivant
    se génèrent ensuite avec l'assistant de clôture ;
  - `opening` : seuls les soldes de fin sont repris en à-nouveaux du premier exercice Lyvre, détaillés
    ligne par ligne (non lettrées) pour les comptes lettrables ; le résultat va en 120 / 129.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.extensions import db
from app.models import (
    Account, AccountMapping, ClosingEvent, Entity, FiscalYear, Journal, JournalEntry, Lettering,
)
from app.models.journal_entry import SOURCE_FEC_IMPORT, SOURCE_OPENING
from app.services.ledger_errors import LedgerError

MAX_SIZE = 20 * 1024 * 1024
REQUIRED = ("JournalCode", "EcritureNum", "EcritureDate", "CompteNum", "EcritureLib")
TIERS_ENTITY = {"401": ("FOURNISSEUR", "account_code"), "411": ("CLIENT", "customer_account_code")}


class ImportError_(LedgerError):  # noqa: N801 — « ImportError » est réservé
    def __init__(self, message, problems=None):
        super().__init__(message)
        self.problems = problems or []


@dataclass
class FecLine:
    journal: str
    journal_label: str
    number: str
    day: date
    account: str
    account_label: str
    aux: str
    aux_label: str
    piece: str
    label: str
    debit: int
    credit: int
    letter: str
    letter_date: date | None

    @property
    def key(self) -> str:
        return f"aux:{self.account}:{self.aux}" if self.aux else self.account


@dataclass
class FecEntry:
    journal: str
    number: str
    day: date
    piece: str
    lines: list = field(default_factory=list)

    @property
    def balance(self) -> int:
        return sum(line.debit - line.credit for line in self.lines)


# ------------------------------------------------------------------ lecture


def decode(content: bytes) -> str:
    if len(content) > MAX_SIZE:
        raise ImportError_("Fichier trop volumineux (20 Mo au plus).")
    for encoding in ("utf-8-sig", "cp1252", "iso-8859-15"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1")


def amount(text: str) -> int:
    """« 1234,56 », « 1 234.56 », « -12 » → centimes ; ValueError si illisible."""
    value = (text or "").strip().replace("\u00a0", "").replace(" ", "")
    if not value:
        return 0
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        return int((Decimal(value) * 100).quantize(Decimal(1), ROUND_HALF_UP))
    except InvalidOperation:
        raise ValueError(text) from None


def ymd(text: str) -> date | None:
    text = (text or "").strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse(content: bytes) -> tuple[list[FecEntry], list[str]]:
    """Écritures du fichier et anomalies (ligne illisible, déséquilibre)."""
    text = decode(content)
    rows = [r for r in re.split(r"\r\n|\n|\r", text) if r.strip()]
    if not rows:
        raise ImportError_("Fichier vide.")
    separator = "\t" if "\t" in rows[0] else "|"
    headers = [h.strip() for h in rows[0].split(separator)]
    missing = [h for h in REQUIRED if h not in headers]
    if missing:
        raise ImportError_(f"Colonnes du FEC manquantes : {', '.join(missing)}.")
    has_debit = "Debit" in headers and "Credit" in headers
    if not has_debit and not ("Montant" in headers and "Sens" in headers):
        raise ImportError_("Colonnes Debit / Credit (ou Montant / Sens) manquantes.")
    entries, problems, by_key = [], [], {}
    for n, row in enumerate(rows[1:], start=2):
        values = row.split(separator)
        rec = dict(zip(headers, (v.strip() for v in values)))
        day = ymd(rec.get("EcritureDate", ""))
        try:
            if has_debit:
                debit, credit = amount(rec.get("Debit", "")), amount(rec.get("Credit", ""))
            else:
                value = amount(rec.get("Montant", ""))
                debit, credit = (value, 0) if rec.get("Sens", "").upper() in ("D", "+1", "1") else (0, value)
        except ValueError:
            problems.append(f"Ligne {n} : montant illisible.")
            continue
        if day is None or not rec.get("CompteNum"):
            problems.append(f"Ligne {n} : date ou compte manquant.")
            continue
        if debit < 0 or credit < 0:  # montant négatif : sens inversé
            debit, credit = max(debit, 0) + max(-credit, 0), max(credit, 0) + max(-debit, 0)
        line = FecLine(rec.get("JournalCode", ""), rec.get("JournalLib", ""), rec.get("EcritureNum", ""), day,
                       rec["CompteNum"], rec.get("CompteLib", ""), rec.get("CompAuxNum", ""), rec.get("CompAuxLib", ""),
                       rec.get("PieceRef", ""), rec.get("EcritureLib", ""), debit, credit, rec.get("EcritureLet", ""),
                       ymd(rec.get("DateLet", "")))
        key = (line.journal, line.number)
        if key not in by_key:
            by_key[key] = FecEntry(line.journal, line.number, day, line.piece)
            entries.append(by_key[key])
        by_key[key].lines.append(line)
    for entry in entries:
        if entry.balance:
            problems.append(f"Écriture {entry.journal}{entry.number} déséquilibrée ({entry.balance / 100:.2f} €).")
    return entries, problems


def closing_date_from_name(filename: str) -> date | None:
    match = re.search(r"FEC(\d{8})", filename or "", re.I)
    return ymd(match.group(1)) if match else None


# ------------------------------------------------------------------ comptes


def _plain(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower())


def _parent_of(code: str) -> Account | None:
    for length in range(len(code) - 1, 0, -1):
        found = Account.query.filter_by(code=code[:length]).first()
        if found is not None:
            return found
    return None


def _free_code(prefix: str, reserved: set) -> str:
    for n in range(1, 1000):
        code = f"{prefix}{n:03d}"
        if code not in reserved and Account.query.filter_by(code=code).first() is None:
            return code
    raise ImportError_(f"Plus de code libre sous {prefix}.")


def plan_accounts(sources: dict[str, dict], overrides: dict | None = None) -> list[dict]:
    """Proposition par compte du fichier : `{key, code, label, aux, aux_label, action, account_id, target_code}`.
    `action` : `existing` (même code), `mapped` (correspondance mémorisée ou choisie), `create`."""
    overrides = overrides or {}
    memo = {m.source_code: m.account_id for m in AccountMapping.query.all()}
    reserved, plan = set(), []
    for key, src in sorted(sources.items()):
        row = {"key": key, "code": src["code"], "label": src["label"], "aux": src.get("aux", ""),
               "aux_label": src.get("aux_label", ""), "action": "create", "account_id": None, "target_code": None}
        chosen = overrides.get(key) or memo.get(key)
        account = db.session.get(Account, chosen) if chosen else None
        if account is not None and not account.is_header:
            row.update(action="mapped", account_id=account.id, target_code=account.code)
        elif not row["aux"]:
            existing = Account.query.filter_by(code=src["code"]).first()
            if existing is not None and not existing.is_header:
                row.update(action="existing", account_id=existing.id, target_code=existing.code)
            else:
                row["target_code"] = src["code"] if existing is None else _free_code(src["code"], reserved)
        else:
            existing = Account.query.filter_by(code=row["aux"]).first() if row["aux"][:1].isdigit() else None
            entity = Entity.query.filter(Entity.name == row["aux_label"]).first() if row["aux_label"] else None
            kind = TIERS_ENTITY.get(src["code"][:3])
            linked = getattr(entity, kind[1]) if entity is not None and kind else None
            if existing is not None and not existing.is_header:
                row.update(action="existing", account_id=existing.id, target_code=existing.code)
            elif linked and Account.query.filter_by(code=linked).first():
                found = Account.query.filter_by(code=linked).first()
                row.update(action="existing", account_id=found.id, target_code=found.code)
            else:
                row["target_code"] = _free_code(src["code"][:3], reserved)
        if row["action"] == "create":
            reserved.add(row["target_code"])
        plan.append(row)
    return plan


def apply_plan(plan: list[dict]) -> dict[str, Account]:
    """Crée les comptes (et fiches de tiers) prévus, mémorise les correspondances ; clé → compte."""
    accounts = {}
    for row in plan:
        if row["action"] in ("existing", "mapped"):
            accounts[row["key"]] = db.session.get(Account, row["account_id"])
        else:
            label = (row["aux_label"] or row["label"] or row["target_code"])[:255]
            account = Account(code=row["target_code"], label=label, account_type="TIERS" if row["aux"] else "OTHER",
                              parent=_parent_of(row["target_code"]))
            db.session.add(account)
            db.session.flush()
            kind = TIERS_ENTITY.get(row["code"][:3])
            if row["aux"] and kind:
                entity = Entity.query.filter(Entity.name == row["aux_label"]).first()
                if entity is None:
                    entity = Entity(name=row["aux_label"] or row["aux"], entity_type=kind[0])
                    db.session.add(entity)
                if not getattr(entity, kind[1]):
                    setattr(entity, kind[1], account.code)
            accounts[row["key"]] = account
        if row["action"] == "mapped" or row["aux"]:
            memo = AccountMapping.query.filter_by(source_code=row["key"]).first()
            if memo is None:
                db.session.add(AccountMapping(source_code=row["key"], account_id=accounts[row["key"]].id))
            else:
                memo.account_id = accounts[row["key"]].id
    db.session.flush()
    return accounts


def _sources(entries: list[FecEntry]) -> dict[str, dict]:
    sources = {}
    for entry in entries:
        for line in entry.lines:
            sources.setdefault(line.key, {"code": line.account, "label": line.account_label, "aux": line.aux,
                                          "aux_label": line.aux_label})
    return sources


def _journals(entries) -> dict[str, Journal]:
    journals = {}
    for entry in entries:
        code = entry.journal[:10] or "OD"
        if code not in journals:
            journal = Journal.query.filter_by(code=code).first()
            if journal is None:
                label = next((l.journal_label for l in entry.lines if l.journal_label), code)
                journal = Journal(code=code, label=label[:100])
                db.session.add(journal)
                db.session.flush()
            journals[code] = journal
    return journals


# ------------------------------------------------------------------ analyse


def analyze(content: bytes, filename: str = "", overrides: dict | None = None) -> dict:
    entries, problems = parse(content)
    if not entries:
        raise ImportError_("Aucune écriture dans le fichier.", problems)
    days = [e.day for e in entries]
    end = closing_date_from_name(filename) or max(days)
    start = min(days).replace(day=1)
    journals = sorted({e.journal for e in entries})
    plan = plan_accounts(_sources(entries), overrides)
    db.session.rollback()  # analyse sans effet
    return {
        "entries": len(entries), "lines": sum(len(e.lines) for e in entries),
        "debit_cents": sum(l.debit for e in entries for l in e.lines),
        "credit_cents": sum(l.credit for e in entries for l in e.lines),
        "first_date": min(days).isoformat(), "last_date": max(days).isoformat(),
        "fiscal_year": {"start_date": start.isoformat(), "end_date": end.isoformat()},
        "journals": [{"code": j, "exists": Journal.query.filter_by(code=j[:10]).first() is not None} for j in journals],
        "letterings": len({(l.key, l.letter) for e in entries for l in e.lines if l.letter}),
        "accounts": plan, "problems": problems[:50],
        "to_create": sum(1 for r in plan if r["action"] == "create"),
    }


# ------------------------------------------------------------------ import


def _log(fy, action, user_id, **details):
    db.session.add(ClosingEvent(fiscal_year_id=fy.id, step="import", action=action, user_id=user_id,
                                details_json=json.dumps(details, default=str, ensure_ascii=False)))


def import_history(content: bytes, filename: str, start: date, end: date, overrides: dict | None = None,
                   user_id=None) -> dict:
    """Historique complet d'un exercice (tout-ou-rien, commit)."""
    from app.services import lettering, validation
    from app.services.ledger import post_entry
    entries, problems = parse(content)
    if problems:
        raise ImportError_(f"{len(problems)} anomalie(s) dans le fichier : rien n'est importé.", problems)
    outside = [e for e in entries if not (start <= e.day <= end)]
    if outside:
        raise ImportError_(f"{len(outside)} écriture(s) hors de l'exercice ({start:%d/%m/%Y} → {end:%d/%m/%Y}).")
    try:
        fy = FiscalYear.query.filter(FiscalYear.start_date <= end, FiscalYear.end_date >= start).first()
        if fy is not None:
            if fy.start_date != start or fy.end_date != end or JournalEntry.query.filter_by(fiscal_year_id=fy.id).first():
                raise ImportError_(f"L'exercice « {fy.label} » existe déjà (dates différentes ou écritures) : "
                                   "importez dans une période libre.")
        else:
            label = str(end.year) if (start.month, start.day) == (1, 1) else f"{start.year}-{end.year}"
            fy = FiscalYear(label=label, start_date=start, end_date=end)
            db.session.add(fy)
            db.session.flush()
        journals = _journals(entries)
        accounts = apply_plan(plan_accounts(_sources(entries), overrides))
        posted, letters = [], {}
        for entry in sorted(entries, key=lambda e: (e.day, e.journal, e.number)):
            rows = [{"account_id": accounts[l.key].id, "label": (l.label or "")[:300], "debit_cents": l.debit,
                     "credit_cents": l.credit} for l in entry.lines]
            created = post_entry(fy.id, journals[entry.journal[:10] or "OD"].id, entry.day,
                                 (entry.lines[0].label or entry.piece or entry.number)[:500], rows,
                                 source=SOURCE_FEC_IMPORT, source_ref=f"{entry.journal}{entry.number}"[:200],
                                 reference=(entry.piece or None) and entry.piece[:50], commit=False)
            posted.append(created)
            for line, model in zip(entry.lines, sorted(created.lines, key=lambda x: x.id)):
                if line.letter:
                    letters.setdefault((model.account_id, line.letter), []).append(model)
        validation.validate(fy, posted, "import", user_id, until=end)
        for (account_id, code), group in letters.items():
            if len(group) < 2 or not db.session.get(Account, account_id).lettrable:
                continue
            item = lettering.letter(group, origin="import", user_id=user_id)
            if not Lettering.query.filter_by(account_id=account_id, code=code[:6]).first():
                item.code = code[:6]  # code d'origine conservé (EcritureLet)
        fy.status = "provisional"
        fy.provisional_at = datetime.utcnow()
        fy.locked_until = end
        _log(fy, "fec_history", user_id, entries=len(posted), file=filename)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return {"fiscal_year_id": fy.id, "fiscal_year": fy.label, "entries": len(posted), "letterings": len(letters)}


def import_opening(content: bytes, filename: str, fy: FiscalYear, overrides: dict | None = None, user_id=None) -> dict:
    """Soldes de fin du fichier en à-nouveaux du premier jour de l'exercice (tout-ou-rien, commit)."""
    from app.services.closing import ClosingError, _result_account
    from app.services.ledger import post_entry
    entries, problems = parse(content)
    if problems:
        raise ImportError_(f"{len(problems)} anomalie(s) dans le fichier : rien n'est importé.", problems)
    if fy.closed:
        raise ImportError_("Exercice clôturé.")
    if JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_OPENING).first():
        raise ImportError_(f"L'exercice « {fy.label} » a déjà des à-nouveaux.")
    try:
        accounts = apply_plan(plan_accounts(_sources(entries), overrides))
        lines = [l for e in entries for l in e.lines]
        groups = {}
        for line in lines:
            if line.letter:
                groups.setdefault((line.key, line.letter), []).append(line)
        settled = {id(l) for group in groups.values() if sum(x.debit - x.credit for x in group) == 0 for l in group}
        rows, balances, result = [], {}, 0
        for line in lines:
            account = accounts[line.key]
            cls = account.code[:1]
            if cls in ("6", "7"):
                result += line.credit - line.debit
            elif cls in "12345":
                if account.lettrable:
                    if id(line) not in settled and (line.debit or line.credit):
                        rows.append({"account_id": account.id, "label": f"{line.piece} {line.day:%d/%m/%Y} — {line.label}"[:300],
                                     "debit_cents": line.debit, "credit_cents": line.credit})
                else:
                    balances[account.id] = balances.get(account.id, 0) + line.debit - line.credit
        for account_id, value in sorted(balances.items()):
            if value:
                rows.append({"account_id": account_id, "label": "Solde repris", "debit_cents": max(value, 0),
                             "credit_cents": max(-value, 0)})
        if result:
            try:
                target = _result_account(result > 0)
            except ClosingError as exc:
                raise ImportError_(exc.message) from None
            rows.append({"account_id": target.id, "label": "Résultat repris", "debit_cents": max(-result, 0),
                         "credit_cents": max(result, 0)})
        journal = Journal.query.filter_by(code="AN").first()
        if journal is None:
            journal = Journal(code="AN", label="À-nouveaux")
            db.session.add(journal)
            db.session.flush()
        entry = post_entry(fy.id, journal.id, fy.start_date, f"À-nouveaux repris ({filename or 'FEC'})"[:500], rows,
                           source=SOURCE_OPENING, source_ref=f"FEC:{filename}"[:200], commit=False)
        _log(fy, "fec_opening", user_id, lines=len(rows), file=filename)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return {"fiscal_year_id": fy.id, "entry_id": entry.id, "reference": entry.reference, "lines": len(rows)}
