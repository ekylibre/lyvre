"""Paramètres réglementaires datés et sourcés (lot AG1.a, claudedocs/design_compta_agricole.md § 4).

Valeurs de référence dans ``data/regulatory/*.json`` (versionnées) ; surcharges saisies par l'administrateur
de la plateforme dans la méta-base (``regulatory_values``), qui l'emportent sur le fichier pour les dates
qu'elles couvrent. Aucun seuil ni taux dans le code : l'appelant reçoit ``MissingParam`` s'il n'existe pas
de valeur à la date demandée et décide (afficher « à confirmer », refuser…).

Clés typées par leur suffixe : ``_cents`` (montant), ``_bp`` (points de base), ``_date`` (AAAA-MM-JJ),
``_years`` / ``_days`` (durées) ; sinon valeur libre (nombre, texte, objet).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "regulatory"
RELIABILITIES = {"V": "Vérifiée", "R": "Règle stable", "A": "Fixée chaque année", "I": "Incertaine"}
KEY_MAX = 120
_RAISE = object()


class MissingParam(LookupError):
    def __init__(self, key: str, on: date):
        super().__init__(f"Paramètre réglementaire « {key} » sans valeur au {on.strftime('%d/%m/%Y')}.")
        self.key, self.on = key, on


class ParamError(ValueError):
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.message, self.field = message, field


@dataclass(frozen=True)
class Param:
    key: str
    value: object
    valid_from: date
    valid_to: date | None
    source: str
    source_label: str
    verified_on: date | None
    reliability: str
    note: str
    origin: str             # "file" | "override"
    id: int | None = None   # surcharge : identifiant en méta-base

    def covers(self, on: date) -> bool:
        return self.valid_from <= on and (self.valid_to is None or on <= self.valid_to)

    def payload(self) -> dict:
        data = asdict(self)
        for name in ("valid_from", "valid_to", "verified_on"):
            data[name] = data[name].isoformat() if data[name] else None
        data["reliability_label"] = RELIABILITIES.get(self.reliability, self.reliability)
        return data


def _date(text) -> date | None:
    return date.fromisoformat(text) if text else None


def _from_dict(raw: dict, origin: str, ident=None) -> Param:
    return Param(key=raw["key"], value=raw.get("value"), valid_from=_date(raw["valid_from"]),
                 valid_to=_date(raw.get("valid_to")), source=raw.get("source") or "",
                 source_label=raw.get("source_label") or "", verified_on=_date(raw.get("verified_on")),
                 reliability=raw.get("reliability") or "A", note=raw.get("note") or "", origin=origin, id=ident)


@lru_cache(maxsize=1)
def file_params() -> tuple[Param, ...]:
    """Valeurs des fichiers ``data/regulatory/*.json`` (le sous-dossier ``sources`` n'est pas lu)."""
    params = []
    for path in sorted(DATA_DIR.glob("*.json")):
        for raw in json.loads(path.read_text(encoding="utf-8"))["values"]:
            params.append(_from_dict(raw, "file"))
    return tuple(params)


def _overrides(prefix: str = "") -> list[Param]:
    """Surcharges de la méta-base (lues à chaque appel : plusieurs processus servent l'application)."""
    from app.extensions import db
    from app.models import RegulatoryValue

    query = db.session.query(RegulatoryValue)
    if prefix:
        query = query.filter(RegulatoryValue.key.startswith(prefix))
    return [_from_dict({"key": row.key, "value": row.value, "valid_from": row.valid_from.isoformat(),
                        "valid_to": row.valid_to.isoformat() if row.valid_to else None, "source": row.source,
                        "source_label": row.source_label,
                        "verified_on": row.verified_on.isoformat() if row.verified_on else None,
                        "reliability": row.reliability, "note": row.note}, "override", row.id)
            for row in query.order_by(RegulatoryValue.valid_from, RegulatoryValue.id)]


def history(key: str) -> list[Param]:
    """Toutes les valeurs connues d'une clé (fichier puis surcharges), par date de début."""
    items = [p for p in file_params() if p.key == key] + [p for p in _overrides(key) if p.key == key]
    return sorted(items, key=lambda p: (p.valid_from, p.origin == "override"))


def get(key: str, on: date | None = None, default=_RAISE) -> Param:
    """Paramètre en vigueur à la date ``on`` (aujourd'hui par défaut) : la surcharge la plus récente qui
    couvre la date, à défaut la valeur du fichier ; ``MissingParam`` (ou ``default``) sinon."""
    on = on or date.today()
    overrides = [p for p in _overrides(key) if p.key == key and p.covers(on)]
    if overrides:
        return max(overrides, key=lambda p: (p.valid_from, p.id or 0))
    files = [p for p in file_params() if p.key == key and p.covers(on)]
    if files:
        return max(files, key=lambda p: p.valid_from)
    if default is _RAISE:
        raise MissingParam(key, on)
    return default


def value(key: str, on: date | None = None, default=_RAISE):
    """Raccourci : la valeur seule."""
    param = get(key, on, default=None)
    if param is None:
        if default is _RAISE:
            raise MissingParam(key, on or date.today())
        return default
    return param.value


def listing(prefix: str = "", on: date | None = None) -> list[dict]:
    """Une ligne par clé : valeur en vigueur à la date (ou None) et historique, pour l'écran d'administration."""
    on = on or date.today()
    keys = sorted({p.key for p in file_params() if p.key.startswith(prefix)}
                  | {p.key for p in _overrides(prefix)})
    rows = []
    for key in keys:
        current = get(key, on, default=None)
        rows.append({"key": key, "domain": key.split(".", 1)[0], "current": current.payload() if current else None,
                     "history": [p.payload() for p in history(key)]})
    return rows


# ------------------------------------------------------------------ surcharges (administrateur)

def _parse_override(data: dict) -> dict:
    clean = {}
    try:
        clean["valid_from"] = date.fromisoformat(str(data.get("valid_from") or ""))
    except ValueError:
        raise ParamError("Date de début attendue (AAAA-MM-JJ).", "valid_from") from None
    text = str(data.get("valid_to") or "").strip()
    try:
        clean["valid_to"] = date.fromisoformat(text) if text else None
    except ValueError:
        raise ParamError("Date de fin attendue (AAAA-MM-JJ).", "valid_to") from None
    if clean["valid_to"] and clean["valid_to"] < clean["valid_from"]:
        raise ParamError("La date de fin précède la date de début.", "valid_to")
    reliability = str(data.get("reliability") or "A").upper()
    if reliability not in RELIABILITIES:
        raise ParamError("Fiabilité : V, R, A ou I.", "reliability")
    clean["reliability"] = reliability
    source = str(data.get("source") or "").strip()
    if not source.startswith(("https://", "http://")):
        raise ParamError("Source officielle obligatoire (adresse https://…).", "source")
    clean["source"] = source[:500]
    clean["source_label"] = str(data.get("source_label") or "").strip()[:200] or None
    clean["note"] = str(data.get("note") or "").strip()[:500] or None
    text = str(data.get("verified_on") or "").strip()
    try:
        clean["verified_on"] = date.fromisoformat(text) if text else date.today()
    except ValueError:
        raise ParamError("Date de vérification attendue (AAAA-MM-JJ).", "verified_on") from None
    if "value" not in data:
        raise ParamError("Valeur obligatoire.", "value")
    clean["value"] = data["value"]
    return clean


def _check_value(key: str, value) -> None:
    if key.endswith(("_cents", "_bp", "_years", "_days")) and not (isinstance(value, int) and not isinstance(value, bool)):
        raise ParamError("Nombre entier attendu (montant en centimes, taux en points de base).", "value")
    if key.endswith("_date"):
        try:
            date.fromisoformat(str(value))
        except ValueError:
            raise ParamError("Date attendue (AAAA-MM-JJ).", "value") from None


def add_override(key: str, data: dict, user_id: int | None = None):
    """Nouvelle surcharge datée d'une clé connue (présente dans un fichier ou déjà surchargée)."""
    from app.extensions import db
    from app.models import RegulatoryValue

    key = (key or "").strip()
    if not key or len(key) > KEY_MAX or not history(key):
        raise ParamError("Paramètre inconnu : ajoutez d'abord la clé dans data/regulatory/.", "key")
    clean = _parse_override(data)
    _check_value(key, clean["value"])
    row = RegulatoryValue(key=key, created_by_user_id=user_id, **{k: v for k, v in clean.items() if k != "value"})
    row.value = clean["value"]
    db.session.add(row)
    db.session.commit()
    return row


def delete_override(override_id: int) -> None:
    from app.extensions import db
    from app.models import RegulatoryValue

    row = db.session.get(RegulatoryValue, override_id)
    if row is None:
        raise ParamError("Surcharge introuvable.")
    db.session.delete(row)
    db.session.commit()
