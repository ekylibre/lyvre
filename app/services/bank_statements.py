"""Relevés de compte mensuels (PDF) : récupération Qonto, stockage, consultation
(claudedocs/design_releves_qonto.md, lot RQ1).

- **Mois visés** : exercice en cours (celui qui contient la date du jour, sinon le dernier ouvert), du
  mois d'ouverture au **dernier mois terminé** — Qonto ne publie que des mois clos.
- **Récupération** (`fetch_qonto`) : liste des relevés du compte (`GET /v2/statements`), puis
  téléchargement aussitôt (le lien expire après 30 minutes ; expiré : lien renouvelé une fois). Un
  relevé déjà stocké avec le même identifiant Qonto et la même taille est ignoré sans téléchargement ;
  sinon il est téléchargé et **remplacé** si son contenu diffère (R4). Lecture seule chez Qonto.
- **Stockage** : `instance/uploads/<instance>/releves/<id du compte>/<AAAA-MM>.pdf`, chemin construit
  ici et vérifié dans le dossier de l'instance ; écriture dans un fichier temporaire puis renommage.
  Le lien Qonto n'est jamais conservé. Aucune suppression (R6).
"""
from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, timedelta
from pathlib import Path

from app.extensions import db
from app.models import BankAccount, BankStatement, FiscalYear
from app.models.bank_statement import SOURCE_QONTO, SOURCE_UPLOAD
from app.services import attachments

STATEMENTS_DIR = "releves"
MAX_SIZE = attachments.MAX_SIZE
EXPIRED_STATUSES = (401, 403, 404, 410)


class StatementError(ValueError):
    pass


# ------------------------------------------------------------------ mois visés

def current_fiscal_year(today: date | None = None) -> FiscalYear | None:
    today = today or date.today()
    fy = FiscalYear.query.filter(FiscalYear.start_date <= today, FiscalYear.end_date >= today).first()
    if fy is not None:
        return fy
    return (FiscalYear.query.filter(FiscalYear.closed.is_(False)).order_by(FiscalYear.end_date.desc()).first())


def months(fy: FiscalYear | None, today: date | None = None) -> list[date]:
    """Premiers jours des mois de l'exercice déjà terminés (le mois en cours n'a pas de relevé)."""
    if fy is None:
        return []
    today = today or date.today()
    last = min(fy.end_date, today.replace(day=1) - timedelta(days=1))
    out, day = [], fy.start_date.replace(day=1)
    while day <= last:
        out.append(day)
        day = (day + timedelta(days=32)).replace(day=1)
    return out


def _qonto_period(day: date) -> str:
    return f"{day:%m-%Y}"


def _parse_period(text: str | None) -> date | None:
    try:
        month, year = (text or "").split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        return None


# ------------------------------------------------------------------ fichiers

def _root() -> Path:
    return attachments.instance_dir()


def relative_path(bank_account: BankAccount, period: date) -> str:
    return f"{STATEMENTS_DIR}/{bank_account.id}/{period:%Y-%m}.pdf"


def path_for(statement: BankStatement) -> Path:
    """Fichier du relevé, vérifié dans le dossier de l'instance."""
    try:
        return attachments._within(_root() / statement.file_path, _root())  # noqa: SLF001 — même contrôle que les pièces
    except attachments.AttachmentError:
        raise StatementError("Chemin de relevé invalide.") from None


def _check_pdf(content: bytes, label: str) -> None:
    if not content.startswith(b"%PDF-"):
        raise StatementError(f"Relevé {label} : le fichier reçu n'est pas un PDF.")
    if len(content) > MAX_SIZE:
        raise StatementError(f"Relevé {label} : fichier de plus de {MAX_SIZE // (1024 * 1024)} Mo.")


def _write(relative: str, content: bytes) -> None:
    target = attachments._within(_root() / relative, _root())  # noqa: SLF001
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(content)
    os.replace(partial, target)


def save(bank_account: BankAccount, period: date, content: bytes, *, source: str, file_name: str | None,
         qonto_id: str | None = None, user_id: int | None = None) -> tuple[BankStatement, str]:
    """Enregistre le relevé du mois (sans commit) : `new`, `replaced` ou `unchanged` (même contenu)."""
    label = f"{period:%m/%Y}"
    _check_pdf(content, label)
    digest = hashlib.sha256(content).hexdigest()
    statement = BankStatement.query.filter_by(bank_account_id=bank_account.id, period=period).first()
    if statement is not None and statement.sha256 == digest:
        statement.qonto_id = qonto_id or statement.qonto_id
        statement.file_size = len(content)
        return statement, "unchanged"
    relative = relative_path(bank_account, period)
    _write(relative, content)
    now = datetime.utcnow()
    outcome = "replaced" if statement is not None else "new"
    if statement is None:
        statement = BankStatement(bank_account_id=bank_account.id, period=period)
        db.session.add(statement)
    else:
        statement.replaced_at = now
    statement.source, statement.qonto_id, statement.file_path = source, qonto_id, relative
    statement.file_name, statement.file_size, statement.sha256 = file_name, len(content), digest
    statement.fetched_at, statement.user_id = now, user_id
    return statement, outcome


# ------------------------------------------------------------------ Qonto

def _download(client, item: dict) -> bytes:
    """PDF du relevé ; lien expiré ou refusé : lien renouvelé par `GET /statements/{id}`, une fois."""
    from app.services.qonto_client import QontoError

    url = (item.get("file") or {}).get("file_url")
    if url:
        try:
            return client.download(url)
        except QontoError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status not in EXPIRED_STATUSES:
                raise
    fresh = client.statement(item["id"])
    url = (fresh.get("file") or {}).get("file_url")
    if not url:
        raise StatementError("Qonto ne donne pas de lien vers ce relevé.")
    return client.download(url)


def fetch_qonto(bank_account: BankAccount, client=None, user_id: int | None = None,
                today: date | None = None) -> dict:
    """Relevés Qonto des mois visés : `{new, replaced, unchanged, errors}` ; commit. Les erreurs d'un
    relevé n'arrêtent pas les autres ; une erreur de la liste remonte (QontoError)."""
    from app.services import qonto_client
    from app.services.qonto_client import QontoError

    if not bank_account.qonto_account_id:
        raise StatementError("Ce compte bancaire n'est pas rattaché à Qonto.")
    result = {"new": 0, "replaced": 0, "unchanged": 0, "errors": []}
    wanted = months(current_fiscal_year(today), today)
    if not wanted:
        return result
    client = client or qonto_client.from_app_config()
    items = client.list_statements(bank_account.qonto_account_id, _qonto_period(wanted[0]), _qonto_period(wanted[-1]))
    stored = {s.period: s for s in BankStatement.query.filter(BankStatement.bank_account_id == bank_account.id,
                                                              BankStatement.period.in_(wanted))}
    for item in items:
        period = _parse_period(item.get("period"))
        if period not in wanted or (item.get("bank_account_id") not in (None, bank_account.qonto_account_id)):
            continue
        file = item.get("file") or {}
        known = stored.get(period)
        if known is not None and known.source == SOURCE_QONTO and known.qonto_id == item.get("id") \
                and known.file_size == file.get("file_size"):
            result["unchanged"] += 1
            continue
        try:
            content = _download(client, item)
            _statement, outcome = save(bank_account, period, content, source=SOURCE_QONTO,
                                       file_name=file.get("file_name"), qonto_id=item.get("id"), user_id=user_id)
            db.session.commit()
            result[outcome] += 1
        except StatementError as exc:
            db.session.rollback()
            result["errors"].append(str(exc))
        except QontoError as exc:
            db.session.rollback()
            status = getattr(getattr(exc, "response", None), "status_code", None)
            result["errors"].append(f"Relevé {period:%m/%Y} : téléchargement impossible"
                                    + (f" (HTTP {status})." if status else "."))
    return result


# ------------------------------------------------------------------ dépôt (lot RQ3)

def upload_months(today: date | None = None) -> list[date]:
    """Mois d'un relevé déposable : mois des exercices ouverts, jusqu'au mois en cours (plus récent d'abord)."""
    today = today or date.today()
    current = today.replace(day=1)
    out = set()
    for fy in FiscalYear.query.filter(FiscalYear.closed.is_(False)):
        day = fy.start_date.replace(day=1)
        while day <= min(fy.end_date, today):
            out.add(day)
            day = (day + timedelta(days=32)).replace(day=1)
    return sorted((d for d in out if d <= current), reverse=True)


def parse_month(text: str | None) -> date | None:
    """« AAAA-MM » → 1er jour du mois."""
    try:
        year, month = (text or "").split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        return None


def store_upload(bank_account: BankAccount, period_text: str | None, file_storage, user_id: int | None = None,
                 today: date | None = None) -> tuple[BankStatement, str]:
    """Relevé PDF déposé pour un compte **hors Qonto** (sur un compte Qonto, la synchronisation le
    remplacerait) ; remplace celui du mois (R4) ; commit. StatementError sinon."""
    if bank_account.qonto_account_id:
        raise StatementError("Ce compte est rattaché à Qonto : ses relevés se récupèrent depuis Qonto.")
    if bank_account.kind != "bank":
        raise StatementError("Une caisse n'a pas de relevé de compte.")
    period = parse_month(period_text)
    if period is None:
        raise StatementError("Choisissez le mois du relevé.")
    if period not in upload_months(today):
        raise StatementError(f"Le mois {period:%m/%Y} n'appartient pas à un exercice ouvert (ou n'a pas commencé).")
    if file_storage is None or not file_storage.filename:
        raise StatementError("Choisissez le fichier PDF du relevé.")
    content = file_storage.stream.read(MAX_SIZE + 1)
    statement, outcome = save(bank_account, period, content, source=SOURCE_UPLOAD,
                              file_name=Path(file_storage.filename).name[:255], user_id=user_id)
    db.session.commit()
    return statement, outcome


# ------------------------------------------------------------------ consultation

def overview(bank_account: BankAccount, today: date | None = None) -> list[dict]:
    """Mois de l'exercice en cours (manquants compris) et relevés stockés d'autres mois, du plus récent
    au plus ancien : `{period, statement}` (statement nul si manquant)."""
    stored = {s.period: s for s in bank_account.statements}
    periods = set(months(current_fiscal_year(today), today)) | set(stored)
    return [{"period": p, "statement": stored.get(p)} for p in sorted(periods, reverse=True)]


# ------------------------------------------------------------------ archive pour l'expert-comptable (lot RQ4)

def for_fiscal_year(fy: FiscalYear) -> list[BankStatement]:
    return (BankStatement.query.filter(BankStatement.period >= fy.start_date.replace(day=1),
                                       BankStatement.period <= fy.end_date)
            .order_by(BankStatement.bank_account_id, BankStatement.period).all())


def _folder(bank_account: BankAccount) -> str:
    from werkzeug.utils import secure_filename
    return secure_filename(bank_account.label or "") or f"compte-{bank_account.id}"


def accountant_archive(fy: FiscalYear, fec_file: tuple[bytes, str] | None, fec_reason: str | None = None,
                       today: date | None = None) -> tuple[bytes, str]:
    """ZIP de l'exercice : `FEC` à la racine (s'il est fourni), `releves/<compte>/<AAAA-MM>.pdf`, et
    `LISEZMOI.txt` (contenu, FEC absent et pourquoi, mois terminés sans relevé par compte bancaire)."""
    import io
    import zipfile

    from werkzeug.utils import secure_filename

    from app.services import organization

    today = today or date.today()
    statements = for_fiscal_year(fy)
    finished = months(fy, today)
    org = organization.get()
    lines = [f"Archive pour l'expert-comptable — {org.name or ''}".rstrip(" —"),
             f"Exercice {fy.label} : du {fy.start_date:%d/%m/%Y} au {fy.end_date:%d/%m/%Y}",
             f"Produite le {datetime.now():%d/%m/%Y à %H:%M} par Lyvre.", ""]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if fec_file is not None:
            content, name = fec_file
            archive.writestr(name, content)
            lines.append(f"FEC : {name}")
        else:
            reason = (fec_reason or "il ne peut pas encore être produit").rstrip(" .")
            lines.append(f"FEC : absent — {reason}.")
        lines += ["", "Relevés de compte (dossier releves/) :"]
        by_account: dict[int, list[BankStatement]] = {}
        for statement in statements:
            by_account.setdefault(statement.bank_account_id, []).append(statement)
        accounts = BankAccount.query.filter(BankAccount.kind == "bank").order_by(BankAccount.label).all()
        for account in accounts:
            stored = by_account.get(account.id, [])
            folder = _folder(account)
            for statement in stored:
                try:
                    archive.write(path_for(statement), f"releves/{folder}/{statement.period:%Y-%m}.pdf")
                except (StatementError, OSError):
                    stored = [s for s in stored if s is not statement]
            present = {s.period for s in stored}
            missing = [m for m in finished if m not in present]
            lines.append(f"- {account.label} : {len(present)} relevé(s)"
                         + (f" ; manquant(s) : {', '.join(f'{m:%m/%Y}' for m in missing)}" if missing else ""))
        if not accounts:
            lines.append("- aucun compte bancaire")
        archive.writestr("LISEZMOI.txt", "\r\n".join(lines) + "\r\n")
    name = f"expert-comptable-{secure_filename(fy.label or '') or fy.id}.zip"
    return buffer.getvalue(), name
