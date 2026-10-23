"""Import CSV des associés (module « Associés », lot A5) : reprise d'une situation (Ekylibre…).

Une ligne par associé et par nature de parts (un associé démembré a plusieurs lignes) :

    nom ; compte ; nature ; parts ; date ; nominal ; solde ; taux

- `nom` (obligatoire) : l'associé existant de ce nom est repris, sinon l'entité de ce nom, sinon
  une entité est créée ;
- `compte` : sous-compte 455 (vide : prochain 4551…) ; `taux` : intérêts annuels en % ;
- `nature` : PP / US / NP (ou « pleine propriété », « usufruit », « nue-propriété ») ; `parts` :
  entier positif ; `date` : date de reprise (JJ/MM/AAAA) ; `nominal` : valeur d'une part ;
- `solde` : solde d'ouverture du compte courant, créditeur positif (la société doit à l'associé).

Deux temps (D13) : `analyse` lit le fichier sans rien écrire ; `run` refait l'analyse et importe
tout ou rien. Les parts deviennent un mouvement « reprise » par date ; un solde devient une
écriture d'à-nouveaux contre le compte choisi, seulement si le compte courant n'a encore aucune
écriture (D14).
"""
from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models import Account, Associate, Entity, Journal
from app.models.associate import ShareMovement, ShareMovementLine
from app.services import associates, share_register
from app.services.associates import AssociateError, next_account_code
from app.services.counterparties import name_key
from app.services.ledger import LedgerError, post_entry
from app.services.purchase_posting import fiscal_year_for

MAX_SIZE = 2 * 1024 * 1024
COLUMNS = ("nom", "compte", "nature", "parts", "date", "nominal", "solde", "taux")
REQUIRED = ("nom", "nature", "parts", "date")
NATURE_WORDS = {
    "pp": "full", "pleinepropriete": "full", "pleinproprietaire": "full", "plein": "full",
    "us": "usufruct", "usufruit": "usufruct", "usufruitier": "usufruct", "usufruitiere": "usufruct",
    "np": "bare", "nuepropriete": "bare", "nupropriete": "bare", "nuproprietaire": "bare",
}
OPENING_JOURNAL = ("AN", "À-nouveaux")
SOURCE = "ASSOCIATE"
TEMPLATE = ("nom;compte;nature;parts;date;nominal;solde;taux\n"
            "Pascal Exemple;4551001;US;300;01/01/2026;10,00;86963,08;0\n"
            "Barbara Exemple;4551002;NP;300;01/01/2026;10,00;500,00;\n"
            "Barbara Exemple;4551002;PP;700;01/01/2026;10,00;;\n")


class ImportFileError(ValueError):
    """Fichier illisible ou refusé dans son ensemble."""


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _rows(content: bytes) -> list[dict]:
    if len(content) > MAX_SIZE:
        raise ImportFileError("Fichier trop volumineux (2 Mo au plus).")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1252", errors="replace")  # export Excel en Windows-1252
    first = text.splitlines()[0] if text.strip() else ""
    delimiter = ";" if first.count(";") >= first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    headers = {h: _plain(h) for h in (reader.fieldnames or [])}
    missing = [c for c in REQUIRED if c not in headers.values()]
    if missing:
        raise ImportFileError(f"Colonnes manquantes : {', '.join(missing)} (attendu : {';'.join(COLUMNS)}).")
    return [{headers[k]: (v or "").strip() for k, v in row.items() if k in headers} for row in reader
            if any((v or "").strip() for v in row.values() if isinstance(v, str))]


def _date(value: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _cents(value: str) -> int | None:
    text = value.replace(" ", "").replace(" ", "").replace("€", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return int((Decimal(text) * 100).quantize(Decimal("1")))
    except InvalidOperation:
        return None


def analyse(content: bytes) -> dict:
    """Lecture complète sans écriture : lignes, associés, mouvements de reprise, erreurs."""
    raw_rows = _rows(content)
    if not raw_rows:
        raise ImportFileError("Fichier vide.")
    rows, people, by_date = [], OrderedDict(), OrderedDict()
    existing = {name_key(a.name): a for a in Associate.query.all()}
    entities = {}
    for e in Entity.query.order_by(Entity.id):
        entities.setdefault(name_key(e.name), e)
    for index, raw in enumerate(raw_rows, start=2):  # ligne 1 : en-têtes
        errors = []
        name = raw.get("nom", "")
        nature = NATURE_WORDS.get(_plain(raw.get("nature", "")))
        parts = int(raw["parts"]) if re.fullmatch(r"\d+", raw.get("parts", "")) else None
        day = _date(raw.get("date", ""))
        nominal = _cents(raw["nominal"]) if raw.get("nominal") else None
        balance = _cents(raw["solde"]) if raw.get("solde") else None
        if not name:
            errors.append("nom manquant")
        if nature is None:
            errors.append(f"nature « {raw.get('nature', '')} » inconnue (PP, US ou NP)")
        if not parts:
            errors.append("parts : entier positif attendu")
        if day is None:
            errors.append("date invalide (JJ/MM/AAAA)")
        if raw.get("nominal") and (nominal is None or nominal <= 0):
            errors.append("nominal invalide")
        if raw.get("solde") and balance is None:
            errors.append("solde invalide")
        rate = None
        if raw.get("taux"):
            try:
                rate = associates.parse_rate(raw["taux"])
            except AssociateError as exc:
                errors.append(str(exc))
        account = raw.get("compte", "")
        if account and not (account.isdigit() and account.startswith("455")):
            errors.append("compte : sous-compte 455 attendu")
        key = name_key(name)
        if name and key not in people:
            associate = existing.get(key)
            people[key] = {"name": name, "associate": associate, "entity": entities.get(key),
                           "account_code": "", "balance_cents": None, "rate_bp": None, "lines": []}
        if name:
            person = people[key]
            # Compte, solde et taux d'un associé : les mêmes sur toutes ses lignes (ou vides).
            for field, value, label in (("account_code", account, "compte"), ("balance_cents", balance, "solde"),
                                        ("rate_bp", rate, "taux")):
                if value in (None, ""):
                    continue
                if person[field] in (None, ""):
                    person[field] = value
                elif person[field] != value:
                    errors.append(f"{label} différent d'une autre ligne de {name}")
        if not errors:
            people[key]["lines"].append((nature, parts))
            group = by_date.setdefault(day, {"nominal": nominal, "lines": []})
            if nominal is not None and group["nominal"] not in (None, nominal):
                errors.append(f"nominal différent d'une autre ligne du {day:%d/%m/%Y}")
            group["nominal"] = group["nominal"] or nominal
            group["lines"].append((key, nature, parts))
        rows.append({"line": index, "name": name, "nature": nature, "parts": parts,
                     "date": day.isoformat() if day else None, "errors": errors})

    errors = []
    for day, group in by_date.items():
        if group["nominal"] is None:
            errors.append(f"Reprise du {day:%d/%m/%Y} : valeur nominale manquante (colonne nominal).")
    # Comptes : proposés pour les nouveaux associés, sans doublon ni compte d'un autre associé.
    taken = {a.account.code: a.name for a in existing.values()}
    reserved = set()
    for person in people.values():
        if person["associate"] is not None:
            person["action"] = "reuse"
            person["account_code"] = person["account_code"] or person["associate"].account.code
            if person["account_code"] != person["associate"].account.code:
                errors.append(f"{person['name']} est déjà associé avec le compte {person['associate'].account.code}.")
            continue
        person["action"] = "create"
        code = person["account_code"]
        if not code:
            code = _next_free_code(reserved)
            person["account_code"] = code
        if code in taken or code in reserved:
            errors.append(f"Compte {code} déjà attribué ({taken.get(code, 'autre ligne du fichier')}).")
        reserved.add(code)
        account = Account.query.filter_by(code=code).first()
        if account is not None and account.is_header:
            errors.append(f"Compte {code} : compte de regroupement.")
    # Soldes : écriture d'ouverture seulement sur un compte courant vierge (D14).
    for person in people.values():
        account = Account.query.filter_by(code=person["account_code"]).first()
        person["balance_action"] = None
        if person["balance_cents"]:
            person["balance_action"] = "ignored" if account is not None and associates.has_entries(account) else "entry"
    # Règles du registre sur chaque mouvement de reprise (nue-propriété = usufruit, etc.).
    for day, group in by_date.items():
        try:
            share_register._check_kind("opening", [(k, n, p) for k, n, p in group["lines"]])
        except share_register.RegisterError as exc:
            errors.append(f"Reprise du {day:%d/%m/%Y} : {exc}")
        fy = fiscal_year_for(day)
        if any(people[k]["balance_action"] == "entry" for k, _n, _p in group["lines"]) and (fy is None or fy.closed):
            errors.append(f"Aucun exercice ouvert au {day:%d/%m/%Y} pour les soldes d'ouverture.")
    line_errors = sum(1 for r in rows if r["errors"])
    return {
        "rows": rows,
        "associates": [{"name": p["name"], "action": p["action"], "account_code": p["account_code"],
                        "parts": {n: sum(q for m, q in p["lines"] if m == n) for n in ("full", "usufruct", "bare")},
                        "balance_cents": p["balance_cents"] or 0, "balance_action": p["balance_action"],
                        "rate": (p["rate_bp"] / 100) if p["rate_bp"] is not None else None}
                       for p in people.values()],
        "movements": [{"date": d.isoformat(), "nominal_cents": g["nominal"], "parts": sum(p for _k, n, p in g["lines"]
                                                                                         if n in ("full", "bare"))}
                       for d, g in by_date.items()],
        "errors": errors, "line_errors": line_errors,
        "needs_counterpart": any(p["balance_action"] == "entry" for p in people.values()),
        "ok": not errors and not line_errors,
        "_people": people, "_by_date": by_date,
    }


def _next_free_code(reserved: set) -> str:
    code = next_account_code()
    number = int(code[4:])
    while code in reserved:
        number += 1
        code = f"4551{number:03d}"
    return code


def public(result: dict) -> dict:
    return {k: v for k, v in result.items() if not k.startswith("_")}


def run(content: bytes, counterpart_code: str | None, user_id=None) -> dict:
    """Importe tout ou rien ; ImportFileError (avec l'analyse) si une erreur subsiste."""
    result = analyse(content)
    if not result["ok"]:
        raise ImportFileError("Le fichier contient des erreurs : rien n'a été importé.")
    counterpart = None
    if result["needs_counterpart"]:
        counterpart = Account.query.filter_by(code=(counterpart_code or "").strip(), is_header=False).first()
        if counterpart is None or counterpart.code.startswith("455"):
            raise ImportFileError("Choisissez le compte de contrepartie des soldes d'ouverture.")
    people, by_date = result["_people"], result["_by_date"]
    created = 0
    try:
        with db.session.no_autoflush:
            for key, person in people.items():
                if person["associate"] is None:
                    entity = person["entity"] or Entity(name=person["name"][:200], entity_type="AUTRE")
                    db.session.add(entity)
                    account = Account.query.filter_by(code=person["account_code"]).first()
                    if account is None:
                        account = Account(code=person["account_code"], label=f"Compte courant — {entity.name}"[:255],
                                          account_type="TIERS", parent=Account.query.filter_by(code="455").first())
                        db.session.add(account)
                    person["associate"] = Associate(entity=entity, account=account, interest_rate_bp=person["rate_bp"])
                    db.session.add(person["associate"])
                    created += 1
                elif person["rate_bp"] is not None:
                    person["associate"].interest_rate_bp = person["rate_bp"]
        db.session.flush()
        for day, group in by_date.items():
            db.session.add(ShareMovement(movement_date=day, kind="opening", nominal_cents=group["nominal"],
                                         description="Reprise importée (CSV)", created_by_id=user_id,
                                         lines=[ShareMovementLine(associate_id=people[k]["associate"].id, nature=n, parts=p)
                                                for k, n, p in group["lines"]]))
        db.session.flush()
        found = share_register._first_negative(share_register._timeline())
        if found is not None:
            raise ImportFileError(str(share_register._negative_error(found, "Import refusé")))
        entries = 0
        journal = _opening_journal() if counterpart is not None else None
        for person in people.values():
            if person["balance_action"] != "entry":
                continue
            day = min(d for d, g in by_date.items() if any(people[k] is person for k, _n, _p in g["lines"]))
            fy = fiscal_year_for(day)
            amount = person["balance_cents"]
            label = f"Reprise du compte courant — {person['name']}"[:255]
            post_entry(fy.id, journal.id, day, label, [
                {"account_id": counterpart.id, "label": label, "debit_cents": max(amount, 0), "credit_cents": max(-amount, 0)},
                {"account_id": person["associate"].account_id, "label": label,
                 "debit_cents": max(-amount, 0), "credit_cents": max(amount, 0)},
            ], source=SOURCE, source_ref=f"OPENING:{person['associate'].id}", commit=False)
            entries += 1
        db.session.commit()
    except (LedgerError, ImportFileError) as exc:
        db.session.rollback()
        raise ImportFileError(str(exc)) from None
    except Exception:
        db.session.rollback()
        raise
    return {"created": created, "reused": len(people) - created, "movements": len(by_date), "entries": entries}


def _opening_journal() -> Journal:
    journal = Journal.query.filter_by(code=OPENING_JOURNAL[0]).first()
    if journal is None:
        journal = Journal(code=OPENING_JOURNAL[0], label=OPENING_JOURNAL[1])
        db.session.add(journal)
        db.session.flush()
    return journal
