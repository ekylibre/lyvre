"""Fichier des écritures comptables (FEC, article A47 A-1 du LPF) et validation des écritures.

- `validate(fy)` : numérotation continue **par journal et par exercice** (ordre date, id) et date
  de validation, attribuées à la clôture provisoire ; recalculée tant que l'exercice n'est pas
  clôturé définitivement (l'ordre est déterministe : les mêmes écritures donnent les mêmes
  numéros) ; `unvalidate(fy)` les efface (réouverture).
- `build(fy)` : fichier texte, 18 champs, première ligne = noms des champs, séparateur
  tabulation, dates AAAAMMJJ, montants à virgule décimale sans séparateur de milliers, encodage
  ISO-8859-15 ; à-nouveaux (journal AN) en tête puis ordre chronologique ; nom
  `<SIREN>FEC<AAAAMMJJ>.txt` (date de clôture de l'exercice).
- `verify(content)` : relecture du fichier produit selon les mêmes règles (contrôle interne ; la
  validation officielle se fait avec l'outil « Test Compta Demat » de la DGFiP).
- `freeze(fy)` : à la clôture définitive, fichier figé dans `instance/uploads/<slug>/fec/` avec
  son empreinte SHA-256.
"""
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models import Account, Entity, FiscalYear, Journal, JournalEntry
from app.models.fiscal_year import FY_OPEN
from app.services import attachments, organization

FIELDS = ("JournalCode", "JournalLib", "EcritureNum", "EcritureDate", "CompteNum", "CompteLib", "CompAuxNum",
          "CompAuxLib", "PieceRef", "PieceDate", "EcritureLib", "Debit", "Credit", "EcritureLet", "DateLet",
          "ValidDate", "Montantdevise", "Idevise")
SEPARATOR = "\t"
ENCODING = "iso-8859-15"
OPENING_JOURNAL = "AN"
TIERS_PREFIXES = ("401", "411")


class FecError(Exception):
    def __init__(self, errors):
        super().__init__(" ".join(errors))
        self.errors = errors


@dataclass
class FecFile:
    filename: str
    content: bytes
    lines: int
    entries: int
    total_debit_cents: int
    total_credit_cents: int
    warnings: list = field(default_factory=list)

    @property
    def sha256(self):
        return hashlib.sha256(self.content).hexdigest()


# ------------------------------------------------------------------ validation des écritures


def _ordered_entries(fy):
    return (JournalEntry.query.filter_by(fiscal_year_id=fy.id)
            .order_by(JournalEntry.journal_id, JournalEntry.entry_date, JournalEntry.id).all())


def validate(fy: FiscalYear, at: datetime | None = None) -> int:
    """Numérote les écritures de l'exercice (continu par journal) ; renvoie leur nombre."""
    if fy.is_final:
        return JournalEntry.query.filter_by(fiscal_year_id=fy.id).count()
    at = at or fy.provisional_at or datetime.utcnow()
    counters = {}
    entries = _ordered_entries(fy)
    for entry in entries:
        counters[entry.journal_id] = counters.get(entry.journal_id, 0) + 1
        entry.validation_number = counters[entry.journal_id]
        entry.validated_at = entry.validated_at if entry.validated_at and entry.validation_number else at
    return len(entries)


def unvalidate(fy: FiscalYear) -> None:
    if fy.is_final:
        raise FecError(["Exercice clôturé définitivement : la validation des écritures est figée."])
    JournalEntry.query.filter_by(fiscal_year_id=fy.id).update(
        {JournalEntry.validation_number: None, JournalEntry.validated_at: None}, synchronize_session=False)


# ------------------------------------------------------------------ format


# Ponctuation typographique hors ISO-8859-15 : équivalent lisible plutôt qu'un « ? ».
_PUNCTUATION = str.maketrans({"—": "-", "–": "-", "‘": "'", "’": "'", "‚": "'", "“": '"', "”": '"', "„": '"',
                              "…": "...", "\u202f": " ", "\u2009": " "})


def clean_text(value) -> str:
    """Texte d'un champ : pas de séparateur ni de retour à la ligne ; ponctuation typographique
    transcrite ; autres caractères hors ISO-8859-15 sans leur accent, sinon « ? »."""
    text = re.sub(r"[\t|\r\n]+", " ", str(value or "")).translate(_PUNCTUATION).strip()
    out = []
    for ch in text:
        try:
            ch.encode(ENCODING)
            out.append(ch)
        except UnicodeEncodeError:
            base = unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode()
            out.append(base or "?")
    return "".join(out)


def amount(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(cents)
    return f"{sign}{cents // 100},{cents % 100:02d}"


def ymd(value) -> str:
    return value.strftime("%Y%m%d") if value else ""


def filename(fy: FiscalYear, siren: str) -> str:
    return f"{siren}FEC{ymd(fy.end_date)}.txt"


# ------------------------------------------------------------------ contrôles et génération


def check(fy: FiscalYear) -> tuple[list[str], list[str]]:
    """Erreurs bloquantes et avertissements avant génération."""
    errors, warnings = [], []
    org = organization.get()
    if not org.siren:
        errors.append("SIREN de la structure manquant (Configuration › Structure).")
    if fy.status == FY_OPEN:
        errors.append("Exercice ouvert : le FEC se génère après la clôture provisoire (écritures validées).")
    entries = _ordered_entries(fy)
    if not entries:
        errors.append("Aucune écriture dans l'exercice.")
    for entry in entries:
        debit = sum(line.debit_cents for line in entry.lines)
        credit = sum(line.credit_cents for line in entry.lines)
        label = entry.reference or f"écriture n° {entry.id}"
        if debit != credit:
            errors.append(f"{label} déséquilibrée ({amount(debit)} au débit, {amount(credit)} au crédit).")
        if not entry.lines:
            errors.append(f"{label} sans ligne.")
        if not (fy.start_date <= entry.entry_date <= fy.end_date):
            errors.append(f"{label} datée hors de l'exercice ({entry.entry_date:%d/%m/%Y}).")
        if fy.status != FY_OPEN and entry.validation_number is None:
            warnings.append(f"{label} non numérotée : numérotation recalculée à la génération.")
    if not any(e.journal and e.journal.code == OPENING_JOURNAL for e in entries) \
            and FiscalYear.query.filter(FiscalYear.end_date < fy.start_date).count():
        warnings.append("Aucun à-nouveau dans l'exercice : le FEC ne reprend pas les soldes d'ouverture "
                        "(à générer avec l'assistant de clôture de l'exercice précédent).")
    return errors[:50], warnings


def build(fy: FiscalYear) -> FecFile:
    """FEC de l'exercice (refus si `check` trouve une erreur bloquante)."""
    errors, warnings = check(fy)
    if errors:
        raise FecError(errors)
    if any(e.validation_number is None for e in JournalEntry.query.filter_by(fiscal_year_id=fy.id)):
        validate(fy)
        db.session.commit()
    siren = organization.get().siren
    journals = {j.id: j for j in Journal.query.all()}
    accounts = {a.id: a for a in Account.query.all()}
    tiers = {e.account_code: e.name for e in Entity.query.filter(Entity.account_code.isnot(None))}

    entries = JournalEntry.query.filter_by(fiscal_year_id=fy.id).all()
    entries.sort(key=lambda e: (journals[e.journal_id].code != OPENING_JOURNAL, e.entry_date,
                                journals[e.journal_id].code, e.validation_number or 0))
    rows = [SEPARATOR.join(FIELDS)]
    total_debit = total_credit = lines = 0
    for entry in entries:
        journal = journals[entry.journal_id]
        number = f"{journal.code}{entry.validation_number:06d}"
        for line in sorted(entry.lines, key=lambda line: line.id):
            account = accounts[line.account_id]
            aux_num = aux_lib = ""
            if account.code.startswith(TIERS_PREFIXES) and account.code in tiers:
                aux_num, aux_lib = account.code, tiers[account.code]
            values = (
                journal.code, journal.label, number, ymd(entry.entry_date), account.code, account.label,
                aux_num, aux_lib, entry.reference or number, ymd(entry.entry_date),
                line.label or entry.description or "", amount(line.debit_cents), amount(line.credit_cents),
                "", "", ymd(entry.validated_at), "", "",
            )
            rows.append(SEPARATOR.join(clean_text(v) for v in values))
            total_debit += line.debit_cents
            total_credit += line.credit_cents
            lines += 1
    content = ("\r\n".join(rows) + "\r\n").encode(ENCODING)
    return FecFile(filename(fy, siren), content, lines, len(entries), total_debit, total_credit, warnings)


# ------------------------------------------------------------------ relecture


def verify(content: bytes) -> list[str]:
    """Contrôle du fichier selon les règles du format ; liste des anomalies (vide = conforme)."""
    problems = []
    text = content.decode(ENCODING)
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", text):
        problems.append("Caractères de contrôle dans le fichier.")
    rows = [r for r in text.split("\r\n") if r != ""]
    if not rows or rows[0].split(SEPARATOR) != list(FIELDS):
        return ["Première ligne : noms des 18 champs attendus, dans l'ordre réglementaire."]
    by_entry, numbers = {}, {}
    total_debit = total_credit = 0
    for n, row in enumerate(rows[1:], start=2):
        values = row.split(SEPARATOR)
        if len(values) != len(FIELDS):
            problems.append(f"Ligne {n} : {len(values)} champs au lieu de {len(FIELDS)}.")
            continue
        rec = dict(zip(FIELDS, values))
        for key in ("JournalCode", "JournalLib", "EcritureNum", "EcritureDate", "CompteNum", "CompteLib",
                    "PieceRef", "PieceDate", "EcritureLib", "ValidDate"):
            if not rec[key]:
                problems.append(f"Ligne {n} : {key} vide.")
        for key in ("EcritureDate", "PieceDate", "ValidDate"):
            if rec[key] and not re.fullmatch(r"\d{8}", rec[key]):
                problems.append(f"Ligne {n} : {key} au format AAAAMMJJ attendu.")
        cents = []
        for key in ("Debit", "Credit"):
            if not re.fullmatch(r"-?\d+,\d{2}", rec[key]):
                problems.append(f"Ligne {n} : {key} au format 1234,56 attendu.")
                cents.append(0)
            else:
                units, dec = rec[key].lstrip("-").split(",")
                cents.append((-1 if rec[key].startswith("-") else 1) * (int(units) * 100 + int(dec)))
        debit, credit = cents
        total_debit += debit
        total_credit += credit
        key = (rec["JournalCode"], rec["EcritureNum"])
        sums = by_entry.setdefault(key, [0, 0])
        sums[0] += debit
        sums[1] += credit
        match = re.fullmatch(rf"{re.escape(rec['JournalCode'])}(\d+)", rec["EcritureNum"])
        if match:
            numbers.setdefault(rec["JournalCode"], set()).add(int(match.group(1)))
    for (journal, number), (debit, credit) in by_entry.items():
        if debit != credit:
            problems.append(f"Écriture {number} ({journal}) déséquilibrée.")
    for journal, found in numbers.items():
        if found != set(range(1, len(found) + 1)):
            problems.append(f"Journal {journal} : numérotation des écritures discontinue.")
    if total_debit != total_credit:
        problems.append("Total des débits différent du total des crédits.")
    return problems[:50]


# ------------------------------------------------------------------ figeage


def freeze(fy: FiscalYear) -> FecFile:
    """FEC figé à la clôture définitive : fichier conservé et empreinte enregistrée (sans commit)."""
    fec_file = build(fy)
    folder = attachments.instance_dir() / "fec"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / fec_file.filename
    path.write_bytes(fec_file.content)
    fy.fec_path = str(path.relative_to(current_app.instance_path))
    fy.fec_sha256 = fec_file.sha256
    return fec_file
