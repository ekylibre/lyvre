"""Mise à jour de la fiche tiers (res.partner) dans Odoo.

Écrit la « date anniversaire » d'adhésion et le statut de l'adhérent dans le
champ **Notes interne** d'Odoo (``res.partner.comment``), pour un ou plusieurs
adhérents.

Le bloc inséré est délimité par des marqueurs : à chaque mise à jour, l'ancien
bloc est remplacé (et non empilé), pour rester idempotent même si la note
contient déjà du texte rédigé à la main par ailleurs.

Le partner Odoo est résolu en deux temps :
1. via ``Order.partner_id`` (commande POS déjà rattachée au tiers) ;
2. à défaut, par recherche ``res.partner`` sur l'email du tiers.

Réutilise ``membership_status`` pour dériver échéance et couleur de statut.
"""
import re
from datetime import date

from app.extensions import db
from app.models import Entity, Order
from app.services import membership_status
from app.services.odoo_client import from_app_config

# Champ Odoo « Notes interne » de res.partner.
PARTNER_NOTE_FIELD = "comment"

# Marqueurs encadrant le bloc géré par l'application.
NOTE_MARKER_START = "[COMPTA-ASSO]"
NOTE_MARKER_END = "[/COMPTA-ASSO]"

_BLOCK_RE = re.compile(
    re.escape(NOTE_MARKER_START) + r".*?" + re.escape(NOTE_MARKER_END),
    re.DOTALL,
)

# Libellé lisible du statut selon la couleur d'échéance.
STATUS_LABELS = {
    "red": "Adhésion expirée",
    "orange": "Adhésion expire bientôt",
    "green": "Adhésion à jour",
}


def build_note_block(birthday, status_info, today=None):
    """Construit le bloc texte géré (entre marqueurs) pour un adhérent."""
    today = today or date.today()
    label = STATUS_LABELS.get(status_info["color"], status_info["color"])
    lines = [
        NOTE_MARKER_START,
        f"Date anniversaire adhésion : {birthday.strftime('%d/%m/%Y')}",
        f"Statut adhésion : {label}",
        f"Mise à jour : {today.strftime('%d/%m/%Y')}",
        NOTE_MARKER_END,
    ]
    return "\n".join(lines)


def merge_into_comment(existing, block):
    """Insère/remplace le bloc géré dans la note existante.

    - Supprime tout bloc géré antérieur (idempotence).
    - Conserve le reste de la note (texte libre saisi dans Odoo).
    - Renvoie la nouvelle valeur du champ ``comment``.
    """
    text = existing or ""
    # Odoo renvoie False quand le champ est vide.
    if text is False:
        text = ""
    cleaned = _BLOCK_RE.sub("", text).strip()
    if cleaned:
        return f"{cleaned}\n\n{block}"
    return block


def _partner_ids_from_orders(entity_ids):
    """Map entity_id -> partner_id Odoo via les commandes POS rattachées."""
    if not entity_ids:
        return {}
    rows = (
        db.session.query(Order.entity_id, db.func.max(Order.partner_id))
        .filter(Order.entity_id.in_(entity_ids))
        .filter(Order.partner_id.isnot(None))
        .group_by(Order.entity_id)
        .all()
    )
    return {eid: pid for eid, pid in rows if pid}


def _partner_ids_from_emails(client, emails):
    """Map email (minuscule) -> partner_id via recherche res.partner."""
    emails = [e for e in emails if e]
    if not emails:
        return {}
    rows = client.search_read(
        "res.partner",
        domain=[["email", "in", emails]],
        fields=["id", "email"],
    )
    result = {}
    for row in rows:
        email = (row.get("email") or "").strip().lower()
        # Première occurrence gagnante (search_read trie par id croissant).
        if email and email not in result:
            result[email] = row["id"]
    return result


def resolve_partner_ids(client, entities):
    """Renvoie {entity_id: partner_id} pour les tiers résolus dans Odoo.

    Priorité aux commandes POS ; repli sur l'email. Les tiers non résolus sont
    simplement absents du dict.
    """
    entity_ids = [e.id for e in entities]
    by_order = _partner_ids_from_orders(entity_ids)

    missing = [e for e in entities if e.id not in by_order and e.email]
    by_email = _partner_ids_from_emails(
        client, [e.email.strip().lower() for e in missing]
    )

    resolved = dict(by_order)
    for e in missing:
        pid = by_email.get(e.email.strip().lower())
        if pid:
            resolved[e.id] = pid
    return resolved


def update_member_notes(rows, today=None, client=None):
    """Met à jour la note Odoo de chaque adhérent des ``rows``.

    ``rows`` : dicts produits par ``membership_status.build_member_rows`` (avec
    ``entity``, ``birthday`` et la couleur de statut).

    Retourne ``{"updated", "skipped", "errors", "error_lines"}``. Une erreur sur
    un tiers n'interrompt pas le lot.
    """
    today = today or date.today()
    client = client or from_app_config()

    entities = [r["entity"] for r in rows if r.get("entity") is not None]
    partner_ids = resolve_partner_ids(client, entities)

    updated = skipped = errors = 0
    error_lines = []

    for row in rows:
        entity = row.get("entity")
        if entity is None:
            skipped += 1
            continue
        partner_id = partner_ids.get(entity.id)
        if not partner_id:
            skipped += 1
            error_lines.append(f"{entity.name} — aucune fiche Odoo trouvée")
            continue
        try:
            status_info = {"color": row["color"]}
            block = build_note_block(row["birthday"], status_info, today)
            current = client.search_read(
                "res.partner",
                domain=[["id", "=", partner_id]],
                fields=[PARTNER_NOTE_FIELD],
                limit=1,
            )
            existing = current[0].get(PARTNER_NOTE_FIELD) if current else ""
            new_comment = merge_into_comment(existing, block)
            client.write("res.partner", partner_id, {PARTNER_NOTE_FIELD: new_comment})
            updated += 1
        except Exception as exc:  # noqa: BLE001 — on isole l'échec par tiers
            errors += 1
            error_lines.append(f"{entity.name} — {exc}")

    return {
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "error_lines": error_lines,
    }


def update_single_member(entity, last_ha, last_pos, today=None, client=None):
    """Met à jour la note Odoo d'un seul adhérent. Retourne (ok, message)."""
    today = today or date.today()
    birthday = membership_status.member_birthday(last_ha, last_pos, today)
    status = membership_status.member_status(last_ha, last_pos, today)
    row = {
        "entity": entity,
        "birthday": birthday,
        "color": status["color"],
    }
    result = update_member_notes([row], today=today, client=client)
    if result["updated"]:
        return True, "Fiche Odoo mise à jour."
    if result["error_lines"]:
        return False, result["error_lines"][0]
    return False, "Aucune fiche Odoo trouvée pour ce tiers."


def is_configured():
    from app.services import external_config
    return external_config.is_available("odoo")
