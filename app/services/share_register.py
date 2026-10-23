"""Registre des parts d'une société (module « Associés », lot A2), hors comptabilité.

Un mouvement daté porte des lignes (associé, nature, parts signées : + reçoit, − cède). La
situation à une date est la somme des lignes jusqu'à cette date (`associates.holdings`). Règles
(claudedocs/design_associes.md §3.1) :

- reprise et souscription : parts reçues seulement ; réduction : parts cédées seulement ;
  valeur nominale obligatoire pour ces trois types (elle fixe le capital) ;
- cession et succession : autant de parts cédées que reçues, nature par nature ;
- donation et réunion de l'usufruit : le capital ne change pas (pleine propriété +
  nue-propriété constante) et la nue-propriété reste égale à l'usufruit ;
- tous types : la nue-propriété et l'usufruit varient du même nombre de parts ; aucune
  situation (associé, nature) ne devient négative, ni à la date du mouvement ni après.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models import Account, Associate, JournalEntry, JournalLine
from app.models.associate import MOVEMENT_KINDS, PART_NATURES, ShareMovement, ShareMovementLine
from app.services import attachments
from app.utils.money import euros

KIND_LABELS = dict(MOVEMENT_KINDS)
NATURE_LABELS = dict(PART_NATURES)
CAPITAL_KINDS = ("opening", "subscription", "reduction")  # changent le capital, portent la valeur nominale
INCOMING_KINDS = ("opening", "subscription")
BALANCED_KINDS = ("transfer", "succession")                # cédé = reçu, nature par nature
NEUTRAL_KINDS = ("donation", "reunion")                    # capital inchangé, démembrement possible
CAPITAL_ACCOUNT_PREFIX = "101"


class RegisterError(ValueError):
    def __init__(self, message, fields=None):
        super().__init__(message)
        self.fields = fields or {}


# ------------------------------------------------------------------ saisie

def _cents(value, field, required=False) -> int | None:
    text = str(value if value is not None else "").replace(" ", "").replace(" ", "").replace("€", "")
    text = text.replace(",", ".")
    if not text:
        if required:
            raise RegisterError("Montant obligatoire.", {field: "Montant obligatoire."})
        return None
    try:
        amount = Decimal(text)
    except InvalidOperation:
        raise RegisterError("Montant invalide.", {field: "Montant invalide."}) from None
    if amount <= 0:
        raise RegisterError("Montant positif attendu.", {field: "Montant positif attendu."})
    return int((amount * 100).quantize(Decimal("1")))


def parse(data: dict) -> dict:
    """Formulaire → `{movement_date, kind, nominal_cents, price_cents, description, lines}` ;
    RegisterError avec les erreurs par champ (`lines.<i>.<champ>`)."""
    errors = {}
    try:
        movement_date = date.fromisoformat(str(data.get("movement_date") or ""))
    except ValueError:
        movement_date = None
        errors["movement_date"] = "Date obligatoire."
    kind = data.get("kind")
    if kind not in KIND_LABELS:
        errors["kind"] = "Type de mouvement inconnu."
    nominal = price = None
    try:
        nominal = _cents(data.get("nominal"), "nominal", required=kind in CAPITAL_KINDS)
    except RegisterError as exc:
        errors.update(exc.fields)
    try:
        price = _cents(data.get("price"), "price")
    except RegisterError as exc:
        errors.update(exc.fields)
    lines = []
    raw_lines = data.get("lines") or []
    if not isinstance(raw_lines, list) or not raw_lines:
        errors["lines"] = "Ajoutez au moins une ligne."
        raw_lines = []
    for i, raw in enumerate(raw_lines):
        raw = raw if isinstance(raw, dict) else {}
        associate = db.session.get(Associate, _int(raw.get("associate_id")) or 0)
        if associate is None:
            errors[f"lines.{i}.associate_id"] = "Choisissez un associé."
        if raw.get("nature") not in NATURE_LABELS:
            errors[f"lines.{i}.nature"] = "Nature inconnue."
        parts = _int(raw.get("parts"))
        if not parts:
            errors[f"lines.{i}.parts"] = "Nombre de parts non nul attendu."
        lines.append((associate.id if associate else None, raw.get("nature"), parts or 0))
    if errors:
        raise RegisterError("Mouvement incomplet ou invalide.", errors)
    return {"movement_date": movement_date, "kind": kind, "nominal_cents": nominal, "price_cents": price,
            "description": str(data.get("description") or "").strip() or None, "lines": lines}


def _int(value) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _check_kind(kind: str, lines) -> None:
    """Règles propres au type de mouvement (indépendantes des autres mouvements)."""
    delta = defaultdict(int)
    for _associate, nature, parts in lines:
        delta[nature] += parts
    if kind in INCOMING_KINDS and any(parts < 0 for _a, _n, parts in lines):
        raise RegisterError(f"{KIND_LABELS[kind]} : uniquement des parts reçues.", {"lines": "Parts reçues seulement."})
    if kind == "reduction" and any(parts > 0 for _a, _n, parts in lines):
        raise RegisterError("Réduction de capital : uniquement des parts cédées (annulées).",
                            {"lines": "Parts cédées seulement."})
    if kind in BALANCED_KINDS:
        unbalanced = [NATURE_LABELS[n] for n, d in delta.items() if d]
        if unbalanced:
            raise RegisterError(f"{KIND_LABELS[kind]} : autant de parts cédées que reçues "
                                f"({', '.join(unbalanced).lower()}).", {"lines": "Cédé ≠ reçu."})
    if kind in NEUTRAL_KINDS and delta["full"] + delta["bare"]:
        raise RegisterError(f"{KIND_LABELS[kind]} : le nombre de parts du capital ne change pas "
                            "(pleine propriété + nue-propriété).", {"lines": "Le capital change."})
    if delta["bare"] != delta["usufruct"]:
        raise RegisterError("Démembrement incomplet : la nue-propriété et l'usufruit doivent porter "
                            "sur le même nombre de parts.", {"lines": "Nue-propriété ≠ usufruit."})


def _timeline(exclude_id=None, extra=None) -> list[tuple[date, int, list]]:
    """Mouvements dans l'ordre (date, id) : [(date, id, [(associé, nature, parts)])]."""
    rows = db.session.query(ShareMovement.movement_date, ShareMovement.id, ShareMovementLine.associate_id,
                            ShareMovementLine.nature, ShareMovementLine.parts) \
        .join(ShareMovementLine).order_by(ShareMovement.movement_date, ShareMovement.id)
    timeline: dict[int, tuple[date, int, list]] = {}
    for day, movement_id, associate_id, nature, parts in rows:
        if movement_id == exclude_id:
            continue
        timeline.setdefault(movement_id, (day, movement_id, []))[2].append((associate_id, nature, parts))
    events = list(timeline.values())
    if extra is not None:
        # Le mouvement saisi passe après ceux de la même date déjà enregistrés.
        events.append((extra[0], float("inf"), extra[1]))
    return sorted(events, key=lambda e: (e[0], e[1]))


def _first_negative(events, since: date | None = None):
    """Premier (date, associé, nature, solde) négatif en appliquant les mouvements dans l'ordre."""
    held = defaultdict(int)
    for index, (day, _id, lines) in enumerate(events):
        for associate_id, nature, parts in lines:
            held[(associate_id, nature)] += parts
        last_of_day = index + 1 == len(events) or events[index + 1][0] != day
        if not last_of_day or (since is not None and day < since):
            continue
        for (associate_id, nature), parts in held.items():
            if parts < 0:
                return day, associate_id, nature, parts
    return None


def _negative_error(found, action="Mouvement refusé") -> RegisterError:
    day, associate_id, nature, parts = found
    name = db.session.get(Associate, associate_id).name
    return RegisterError(f"{action} : {name} aurait {parts} part(s) en {NATURE_LABELS[nature].lower()} "
                         f"au {day:%d/%m/%Y}.", {"lines": "Parts insuffisantes."})


def validate(clean: dict, exclude_id=None) -> None:
    _check_kind(clean["kind"], clean["lines"])
    events = _timeline(exclude_id, (clean["movement_date"], clean["lines"]))
    found = _first_negative(events)
    if found is not None:
        raise _negative_error(found)


def situation_after(clean: dict, exclude_id=None) -> dict[int, dict[str, int]]:
    """Parts par associé et nature juste après le mouvement (prévisualisation)."""
    held: dict[int, dict[str, int]] = defaultdict(lambda: dict.fromkeys(NATURE_LABELS, 0))
    for day, _id, lines in _timeline(exclude_id, (clean["movement_date"], clean["lines"])):
        if day > clean["movement_date"]:
            break
        for associate_id, nature, parts in lines:
            held[associate_id][nature] += parts
    return held


def _apply(movement: ShareMovement, clean: dict, token: str | None) -> None:
    movement.movement_date = clean["movement_date"]
    movement.kind = clean["kind"]
    movement.nominal_cents = clean["nominal_cents"]
    movement.price_cents = clean["price_cents"]
    movement.description = clean["description"]
    movement.lines = [ShareMovementLine(associate_id=a, nature=n, parts=p) for a, n, p in clean["lines"]]
    db.session.flush()
    if token:
        attachments.store(movement, token, folder="parts", day=movement.movement_date)


def create(data: dict, token: str | None = None, user_id=None) -> ShareMovement:
    clean = parse(data)
    validate(clean)
    movement = ShareMovement(created_by_id=user_id)
    db.session.add(movement)
    try:
        _apply(movement, clean, token)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return movement


def update(movement: ShareMovement, data: dict, token: str | None = None) -> ShareMovement:
    clean = parse(data)
    validate(clean, exclude_id=movement.id)
    try:
        _apply(movement, clean, token)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return movement


def delete(movement: ShareMovement) -> None:
    """Suppression refusée si un mouvement postérieur s'appuie dessus (situation négative)."""
    found = _first_negative(_timeline(exclude_id=movement.id))
    if found is not None:
        raise _negative_error(found, "Suppression impossible")
    path = attachments.path_of(movement)
    db.session.delete(movement)
    db.session.commit()
    if path is not None:
        path.unlink(missing_ok=True)


# ------------------------------------------------------------------ capital

def nominal_at(at: date | None) -> int | None:
    query = ShareMovement.query.filter(ShareMovement.nominal_cents.isnot(None))
    if at is not None:
        query = query.filter(ShareMovement.movement_date <= at)
    last = query.order_by(ShareMovement.movement_date.desc(), ShareMovement.id.desc()).first()
    return last.nominal_cents if last else None


def ledger_capital(at: date | None) -> int:
    """Solde créditeur des comptes 101… (capital) à la date."""
    query = db.session.query(db.func.coalesce(db.func.sum(JournalLine.credit_cents - JournalLine.debit_cents), 0)) \
        .join(JournalEntry).join(Account, JournalLine.account_id == Account.id) \
        .filter(Account.code.like(f"{CAPITAL_ACCOUNT_PREFIX}%"))
    if at is not None:
        query = query.filter(JournalEntry.entry_date <= at)
    return int(query.scalar() or 0)


def capital(at: date | None, held: dict[int, dict[str, int]]) -> dict:
    """Parts, nominal, capital, solde du 101 et contrôles (écarts signalés, jamais bloquants)."""
    parts = sum(h["full"] + h["bare"] for h in held.values())
    bare = sum(h["bare"] for h in held.values())
    usufruct = sum(h["usufruct"] for h in held.values())
    nominal = nominal_at(at)
    amount = parts * nominal if nominal is not None else None
    ledger = ledger_capital(at)
    warnings = []
    if bare != usufruct:
        warnings.append(f"Nue-propriété ({bare} parts) et usufruit ({usufruct} parts) ne s'équilibrent pas.")
    if amount is not None and amount != ledger:
        warnings.append(f"Capital du registre ({euros(amount)}) différent du solde des comptes 101 ({euros(ledger)}).")
    return {"parts": parts, "nominal_cents": nominal, "capital_cents": amount, "ledger_cents": ledger,
            "warnings": warnings}


# ------------------------------------------------------------------ lecture

def payload(movement: ShareMovement) -> dict:
    return {
        "id": movement.id, "movement_date": movement.movement_date.isoformat(), "kind": movement.kind,
        "kind_label": KIND_LABELS.get(movement.kind, movement.kind),
        "nominal_cents": movement.nominal_cents, "price_cents": movement.price_cents,
        "description": movement.description,
        "attachment": ({"name": movement.attachment_name, "url": f"/api/v1/share-movements/{movement.id}/attachment"}
                       if movement.attachment_path else None),
        "lines": [{"associate_id": line.associate_id, "associate": line.associate.name, "nature": line.nature,
                   "nature_label": NATURE_LABELS[line.nature], "parts": line.parts} for line in movement.lines],
    }


def movements(associate_id: int | None = None, until: date | None = None) -> list[ShareMovement]:
    query = ShareMovement.query
    if associate_id is not None:
        query = query.filter(ShareMovement.lines.any(ShareMovementLine.associate_id == associate_id))
    if until is not None:
        query = query.filter(ShareMovement.movement_date <= until)
    return query.order_by(ShareMovement.movement_date.desc(), ShareMovement.id.desc()).all()
