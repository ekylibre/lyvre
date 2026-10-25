"""Mise à jour groupée des tiers depuis Sirene (lot G5) : tâche de fond qui lit Sirene par paquets de
100 tiers (3 appels par paquet : unités légales, établissements des tiers qui ont un SIRET, sièges
de ceux qui n'ont qu'un SIREN), puis compare chaque tiers à sa proposition. Rien n'est écrit : le
résultat attend la revue, qui applique les champs choisis (`apply`), avec un verrou optimiste.
"""
from __future__ import annotations

import threading

from app.extensions import db
from app.models import Entity
from app.services import sirene
from app.services.organization import luhn_valid

# Champs comparés, dans l'ordre de la revue.
FIELDS = {"name": "Nom", "person_kind": "Nature", "address_line1": "Adresse", "address_line2": "Complément d'adresse",
          "postal_code": "Code postal", "city": "Ville", "country": "Pays", "vat_number": "N° de TVA",
          "siret": "SIRET", "siren": "SIREN", "naf_code": "Activité (NAF)"}
STATES = {"changes": "À revoir", "up_to_date": "À jour", "ceased": "Cessé ou fermé", "not_found": "Introuvable",
          "invalid": "Numéro invalide"}

_cancelled: set[int] = set()  # jobs dont l'arrêt est demandé (un seul processus, cf. sirene.limiter)
_lock = threading.Lock()


def cancel(job_id: int) -> None:
    with _lock:
        _cancelled.add(job_id)


def _is_cancelled(job_id: int) -> bool:
    with _lock:
        return job_id in _cancelled


def _norm(value) -> str:
    return " ".join(str(value or "").split()).casefold()


def candidates(entity_ids: list[int] | None = None) -> list[Entity]:
    """Tiers qui ont un SIREN ou un SIRET : parmi ceux choisis, ou tous."""
    query = Entity.query.filter(db.or_(Entity.siren.isnot(None), Entity.siret.isnot(None)))
    if entity_ids:
        query = query.filter(Entity.id.in_(entity_ids))
    return query.order_by(Entity.name).all()


def _numbers(entity: Entity) -> tuple[str | None, str | None]:
    """(SIREN, SIRET) valides du tiers ; (None, None) si aucun numéro n'est exploitable."""
    siret = entity.siret if entity.siret and len(entity.siret) == 14 and entity.siret.isdigit() else None
    siren = siret[:9] if siret else entity.siren
    if not siren or not (len(siren) == 9 and siren.isdigit() and luhn_valid(siren)):
        return None, None
    return siren, siret


def changes(entity: Entity, values: dict, computed: list[str]) -> list[dict]:
    """Champs à compléter (vides en base) et champs différents de Sirene."""
    out = []
    for key, label in FIELDS.items():
        proposed = values.get(key)
        if not proposed:
            continue
        current = getattr(entity, key) or ""
        if _norm(current) == _norm(proposed):
            continue
        out.append({"field": key, "label": label, "current": current or None, "proposed": proposed,
                    "computed": key in computed, "kind": "different" if current else "empty"})
    return out


def _item(entity: Entity, state: str, *, changes_=None, warnings=None, nomenclature=None) -> dict:
    return {"entity_id": entity.id, "name": entity.name, "state": state, "state_label": STATES[state],
            "changes": changes_ or [], "warnings": warnings or [], "naf_nomenclature": nomenclature}


def run(entity_ids: list[int] | None, job_id: int, progress=None) -> dict:
    """Corps de la tâche : propositions de tous les tiers, sans rien modifier."""
    entities = candidates(entity_ids)
    total = len(entities)
    items, done, cancelled = [], 0, False
    for start in range(0, total, sirene.BATCH):
        if _is_cancelled(job_id):
            cancelled = True
            break
        batch = entities[start:start + sirene.BATCH]
        numbers = {e.id: _numbers(e) for e in batch}
        sirens = sorted({siren for siren, _siret in numbers.values() if siren})
        sirets = sorted({siret for _siren, siret in numbers.values() if siret})
        units = sirene.legal_units(sirens, background=True) if sirens else {}
        establishments = sirene.establishments(sirets, background=True) if sirets else {}
        without = sorted({siren for siren, siret in numbers.values() if siren and not siret})
        heads = sirene.head_offices(without, background=True) if without else {}
        for entity in batch:
            siren, siret = numbers[entity.id]
            if siren is None:
                items.append(_item(entity, "invalid"))
            elif siren not in units:
                items.append(_item(entity, "not_found"))
            else:
                est = establishments.get(siret) if siret else heads.get(siren)
                warnings = ["SIRET inconnu de Sirene : seule l'unité légale est comparée."] if siret and est is None else []
                proposal = sirene.build_proposal(units[siren], est, for_entity=True)
                if proposal.state == "ceased":
                    items.append(_item(entity, "ceased", warnings=warnings + proposal.warnings))
                else:
                    found = changes(entity, proposal.values, proposal.computed)
                    items.append(_item(entity, "changes" if found else "up_to_date", changes_=found,
                                       warnings=warnings + proposal.warnings,
                                       nomenclature=proposal.values.get("naf_nomenclature")))
            done += 1
        if progress:
            progress(done, total, f"{done} tiers sur {total} comparés à Sirene…")
    with _lock:
        _cancelled.discard(job_id)
    counts = {state: sum(1 for i in items if i["state"] == state) for state in STATES}
    return {"items": items, "total": total, "compared": done, "cancelled": cancelled, **counts}


def apply(result: dict, selection: dict) -> dict:
    """Applique les champs choisis `{entity_id: [champs]}` en une transaction. Un champ dont la valeur
    a changé en base depuis la revue est sauté (verrou optimiste), comme un nom déjà pris."""
    by_id = {str(i["entity_id"]): i for i in result.get("items", [])}
    applied, skipped = 0, []
    for entity_id, fields in (selection or {}).items():
        item = by_id.get(str(entity_id))
        entity = db.session.get(Entity, int(entity_id)) if str(entity_id).isdigit() else None
        if item is None or entity is None:
            skipped.append({"entity_id": entity_id, "field": None, "reason": "Tiers absent de la revue."})
            continue
        proposed = {c["field"]: c for c in item["changes"]}
        for field in fields or []:
            change = proposed.get(field)
            if change is None:
                skipped.append({"entity_id": entity.id, "field": field, "reason": "Champ non proposé."})
                continue
            if _norm(getattr(entity, field)) != _norm(change["current"]):
                skipped.append({"entity_id": entity.id, "field": field,
                                "reason": "Modifié depuis la revue : valeur conservée."})
                continue
            if field == "name" and Entity.query.filter(Entity.name == change["proposed"], Entity.id != entity.id).first():
                skipped.append({"entity_id": entity.id, "field": field,
                                "reason": f"Un autre tiers s'appelle déjà « {change['proposed']} »."})
                continue
            setattr(entity, field, change["proposed"])
            if field == "naf_code":
                entity.naf_nomenclature = item.get("naf_nomenclature")
            applied += 1
    db.session.commit()
    return {"applied": applied, "skipped": skipped}
