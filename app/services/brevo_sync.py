"""Synchronisation des adhérents vers une liste Brevo (lot B2, conception §3).

Un adhérent = un contact Brevo, lié une fois pour toutes (`BrevoLink`) : ensuite retrouvé par
l'identifiant du contact, jamais recherché par e-mail ni recréé. Chaque passage lit tout le compte
(500 contacts par page), classe chaque adhérent, puis écrit (sauf aperçu). Lyvre n'envoie jamais
`emailBlacklisted`, `forceMerge` ni `updateEnabled` ; il ne change jamais l'e-mail d'un contact
désinscrit (Brevo le réinscrirait) et ne supprime jamais de contact.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime

from app.extensions import db
from app.models import Entity, HelloAssoItem, HelloAssoOrder
from app.models.brevo_link import BREVO_CONFLICT, BREVO_LINKED, BREVO_REMOVED, BrevoLink
from app.queries.entities import last_membership_dates
from app.services import brevo_attributes, brevo_client, external_config
from app.services.membership_status import member_birthday, member_status

STATUS_LABELS = {"green": "À jour", "orange": "Expire bientôt", "red": "Échue"}
DECISIONS = ("created", "linked", "updated", "unchanged", "unlinked", "conflicts", "skipped", "errors")


class SyncError(Exception):
    pass


def normalize(email: str | None) -> str:
    return (email or "").strip().lower()


def ext_id(entity_id: int) -> str:
    from app.tenant import current_instance
    slug = getattr(current_instance(), "slug", None) or "instance"
    return f"lyvre-{slug}-{entity_id}"


def has_links() -> bool:
    """Une synchronisation a déjà écrit dans Brevo (au moins un adhérent lié)."""
    return db.session.query(BrevoLink.id).first() is not None


def first_sync_pending() -> bool:
    """Ni lien ni aperçu abouti : la première synchronisation doit être précédée d'un aperçu (D3)."""
    if has_links():
        return False
    from app.models import SyncJob
    from app.models.sync_job import SYNC_KIND_BREVO, SYNC_STATUS_DONE
    previews = SyncJob.query.filter_by(kind=SYNC_KIND_BREVO, status=SYNC_STATUS_DONE).all()
    return not any('"dry_run": true' in (j.result_json or "") for j in previews)


# ------------------------------------------------------------------ valeurs envoyées


def _iso(value) -> str | None:
    if value is None:
        return None
    return (value.date() if isinstance(value, datetime) else value).isoformat()


def _names(entity_ids: list[int]) -> dict[int, tuple[str | None, str | None]]:
    """Prénom et nom par adhérent : dernier article HelloAsso nominatif, sinon payeur de la
    dernière commande. Le nom Lyvre (un seul champ) n'est jamais découpé."""
    out: dict[int, tuple[str | None, str | None]] = {}
    if not entity_ids:
        return out
    items = (HelloAssoItem.query.filter(HelloAssoItem.entity_id.in_(entity_ids))
             .order_by(HelloAssoItem.id.desc()).all())
    for it in items:
        if it.entity_id not in out and (it.user_first_name or it.user_last_name):
            out[it.entity_id] = (it.user_first_name, it.user_last_name)
    orders = (HelloAssoOrder.query.filter(HelloAssoOrder.entity_id.in_(entity_ids))
              .order_by(HelloAssoOrder.date.desc().nullslast()).all())
    for o in orders:
        if o.entity_id not in out and (o.payer_first_name or o.payer_last_name):
            out[o.entity_id] = (o.payer_first_name, o.payer_last_name)
    return out


@dataclass
class Member:
    entity: Entity
    email: str
    managed: dict          # attributs tenus par Lyvre
    shared: dict           # attributs complétés seulement s'ils sont vides dans Brevo

    @property
    def hash(self) -> str:
        return hashlib.sha256(json.dumps({"email": self.email, **self.managed}, sort_keys=True).encode()).hexdigest()


def members(entity_ids: list[int] | None = None, today: date | None = None) -> list[Member]:
    query = Entity.query.filter_by(entity_type="ADHERENT")
    if entity_ids:
        query = query.filter(Entity.id.in_(entity_ids))
    entities = query.order_by(Entity.id).all()
    ids = [e.id for e in entities]
    last_ha, last_pos = last_membership_dates(ids)
    names = _names(ids)
    out = []
    for e in entities:
        ha, pos = last_ha.get(e.id), last_pos.get(e.id)
        known = ha is not None or pos is not None
        last = max((d for d in (_iso(ha), _iso(pos)) if d), default=None)
        status = member_status(ha, pos, today)
        first, last_name = names.get(e.id, (None, None))
        out.append(Member(e, normalize(e.email), {
            "DATE_ADH": last,
            "LYVRE_STATUT": STATUS_LABELS[status["color"]] if known else "Inconnue",
            "LYVRE_ECHEANCE": _iso(member_birthday(ha, pos, today)) if known else None,
            "LYVRE_BENEVOLE": bool(e.is_benevole),
        }, {"PRENOM": first, "NOM": last_name}))
    return out


# ------------------------------------------------------------------ plan


@dataclass
class Plan:
    """Décisions d'un passage, avant écriture (l'aperçu s'arrête là)."""
    creates: list = field(default_factory=list)      # (Member,)
    updates: list = field(default_factory=list)      # (Member, contact, link | None, row)
    unchanged: list = field(default_factory=list)    # (Member, contact, link)
    unlinks: list = field(default_factory=list)      # BrevoLink
    conflicts: list = field(default_factory=list)    # (Member | None, link | None, motif)
    skipped: list = field(default_factory=list)      # (Member, motif)
    blacklisted: list = field(default_factory=list)  # Member
    orphans: int = 0                                 # contacts de la liste sans adhérent lié


def _row(member: Member, contact: dict | None, list_id: int, present: set[str], new_email: bool) -> dict:
    """Champs à envoyer pour un contact existant (vide : rien à faire)."""
    attrs = contact.get("attributes") or {} if contact else {}
    row: dict = {}
    managed = {k: v for k, v in member.managed.items() if v is not None and k in present and attrs.get(k) != v}
    shared = {k: v for k, v in member.shared.items() if v and k in present and not attrs.get(k)}
    if managed or shared:
        row["attributes"] = {**managed, **shared}
    if new_email:
        row.setdefault("attributes", {})["EMAIL"] = member.email
    if list_id not in (contact.get("listIds") or []):
        row["listIds"] = [list_id]
    if attrs.get("EXT_ID") != ext_id(member.entity.id):
        row["ext_id"] = ext_id(member.entity.id)
    return row


def plan(contacts: list[dict], list_id: int, present: set[str], entity_ids: list[int] | None = None) -> Plan:
    result = Plan()
    by_id = {c["id"]: c for c in contacts}
    by_email = {normalize(c.get("email")): c for c in contacts if c.get("email")}
    by_ext = {(c.get("attributes") or {}).get("EXT_ID"): c for c in contacts if (c.get("attributes") or {}).get("EXT_ID")}
    links = {l.entity_id: l for l in BrevoLink.query.all()}
    linked_contacts = {l.contact_id: l for l in links.values() if l.state != BREVO_REMOVED}
    seen_members, claimed = set(), set()

    for m in members(entity_ids):
        seen_members.add(m.entity.id)
        if not m.email or "@" not in m.email:
            result.skipped.append((m, "Adhérent sans e-mail."))
            continue
        link = links.get(m.entity.id)
        contact = by_id.get(link.contact_id) if link else None  # même après une sortie de la liste
        if contact is None:  # jamais lié, ou contact supprimé dans Brevo : rapprochement
            contact = by_ext.get(ext_id(m.entity.id)) or by_email.get(m.email)
            owner = linked_contacts.get(contact["id"]) if contact else None
            if contact is not None and ((owner is not None and owner.entity_id != m.entity.id) or contact["id"] in claimed):
                result.conflicts.append((m, link, "E-mail déjà lié dans Brevo à un autre adhérent."))
                continue
        if contact is None:
            other = by_email.get(m.email)
            if other is not None and other["id"] in linked_contacts:
                result.conflicts.append((m, link, "E-mail déjà utilisé dans Brevo par un autre adhérent lié."))
            else:
                result.creates.append(m)
            continue
        claimed.add(contact["id"])
        if contact.get("emailBlacklisted"):
            result.blacklisted.append(m)
        new_email = normalize(contact.get("email")) != m.email
        if new_email:
            other = by_email.get(m.email)
            if other is not None and other["id"] != contact["id"]:
                result.conflicts.append((m, link, "Nouvel e-mail déjà utilisé dans Brevo par un autre contact."))
                continue
            if contact.get("emailBlacklisted"):
                result.conflicts.append((m, link, "Contact désinscrit : changer son e-mail le réinscrirait. "
                                                  "À traiter dans Brevo."))
                continue
        row = _row(m, contact, list_id, present, new_email)
        if row or link is None or link.payload_hash != m.hash or link.state != BREVO_LINKED:
            result.updates.append((m, contact, link, row))
        else:
            result.unchanged.append((m, contact, link))

    if entity_ids is None:  # passage complet : sorties de la liste
        current = {m.entity.id for m in members() if m.email}
        for link in links.values():
            if link.state == BREVO_REMOVED:
                continue
            gone = link.entity_id is None or link.entity_id not in current
            if gone:
                result.unlinks.append(link)
        listed = {c["id"] for c in contacts if list_id in (c.get("listIds") or [])}
        result.orphans = len(listed - {l.contact_id for l in links.values() if l.state != BREVO_REMOVED}
                             - {u[1]["id"] for u in result.updates if u[1]} - claimed)
    return result


# ------------------------------------------------------------------ passage


def _settings() -> tuple[brevo_client.Client, int]:
    list_id = external_config.get("brevo", "list_id")
    if not (list_id or "").strip().isdigit():
        raise SyncError("Choisissez la liste des adhérents dans Configuration › Intégrations › Brevo.")
    return brevo_client.Client.from_config(), int(list_id)


def _link(member: Member, contact_id: int, link: BrevoLink | None) -> BrevoLink:
    """Lien de l'adhérent (réutilisé : contact recréé, retour dans la liste), pointé sur ce contact."""
    link = link or BrevoLink.query.filter_by(entity_id=member.entity.id).first()
    stale = BrevoLink.query.filter(BrevoLink.contact_id == contact_id)
    stale = (stale.filter(BrevoLink.id != link.id) if link else stale).first()
    if stale is not None:  # ancien lien d'un tiers sorti, sur le même contact
        db.session.delete(stale)
        db.session.flush()
    if link is None:
        link = BrevoLink(entity_id=member.entity.id, contact_id=contact_id)
        db.session.add(link)
    link.entity_id, link.contact_id = member.entity.id, contact_id
    link.email, link.payload_hash, link.in_list = member.email, member.hash, True
    link.state, link.note, link.synced_at = BREVO_LINKED, None, datetime.utcnow()
    return link


def _summary(p: Plan, *, dry_run: bool, errors: list[dict], created: int, linked: int) -> dict:
    who = lambda m: {"entity_id": m.entity.id, "name": m.entity.name}  # noqa: E731
    return {
        "dry_run": dry_run,
        "created": len(p.creates) if dry_run else created,
        "linked": sum(1 for u in p.updates if u[2] is None) if dry_run else linked,
        "updated": sum(1 for u in p.updates if u[2] is not None), "unchanged": len(p.unchanged), "unlinked": len(p.unlinks),
        "conflicts": len(p.conflicts), "skipped": len(p.skipped), "blacklisted": len(p.blacklisted),
        "orphans": p.orphans, "errors": [f"{e['name']} : {e['reason']}" for e in errors],
        "conflict_items": [{**(who(m) if m else {"entity_id": None, "name": "Tiers supprimé"}), "reason": r}
                           for m, _l, r in p.conflicts],
        "blacklisted_items": [who(m) for m in p.blacklisted],
        "skipped_items": [{**who(m), "reason": r} for m, r in p.skipped],
    }


def run(*, dry_run: bool, entity_ids: list[int] | None = None, progress=None) -> dict:
    """Un passage (aperçu ou écriture) ; renvoie le rapport rangé dans le job."""
    client, list_id = _settings()
    present = {a.get("name") for a in client.attributes() if a.get("category", "normal") == "normal"}
    if progress:
        progress(0, None, "Lecture des contacts Brevo…")
    contacts = client.contacts()
    p = plan(contacts, list_id, present, entity_ids)
    errors: list[dict] = []
    created = linked = 0
    if not dry_run:
        for m, link, reason in p.conflicts:
            if link is not None:
                link.state, link.note = BREVO_CONFLICT, reason[:300]
        total, done = len(p.creates) + len(p.updates) + len(p.unlinks), 0
        for m in p.creates:
            attrs = {k: v for k, v in {**m.managed, **m.shared}.items() if v not in (None, "") and k in present}
            try:
                contact_id = client.create_contact(m.email, ext_id(m.entity.id), attrs, [list_id])
                if contact_id:
                    _link(m, contact_id, None)
                    created += 1
            except brevo_client.BrevoError as exc:
                errors.append({"name": m.entity.name, "reason": exc.message})
            done += 1
            if progress:
                progress(done, total, f"{done} contact(s) traité(s) sur {total}…")
            db.session.commit()
        rows = [(m, c, l, {"id": c["id"], **r}) for m, c, l, r in p.updates if r]
        failed: set[int] = set()
        try:
            if rows:
                client.update_batch([r for *_x, r in rows])
        except brevo_client.BrevoError:
            for m, c, _l, r in rows:  # paquet refusé : contact par contact, pour isoler le fautif
                try:
                    client.update_contact(c["id"], {k: v for k, v in r.items() if k != "id"})
                except brevo_client.BrevoError as exc:
                    failed.add(c["id"])
                    errors.append({"name": m.entity.name, "reason": exc.message})
        for m, c, l, _r in p.updates:
            if c["id"] not in failed:
                linked += l is None
                _link(m, c["id"], l)
        done += len(p.updates)
        if progress:
            progress(done, total, f"{done} contact(s) traité(s) sur {total}…")
        unlink_ids = [l.contact_id for l in p.unlinks]
        if unlink_ids:
            try:
                client.unlink(list_id, unlink_ids)
                for l in p.unlinks:
                    l.state, l.in_list, l.synced_at = BREVO_REMOVED, False, datetime.utcnow()
            except brevo_client.BrevoError as exc:
                errors.append({"name": "Retrait de la liste", "reason": exc.message})
        db.session.commit()
    return _summary(p, dry_run=dry_run, errors=errors, created=created, linked=linked)


def start(app, *, dry_run: bool, entity_ids: list[int] | None = None):
    """Lance un passage en arrière-plan (job `brevo_sync`), ou renvoie celui en cours."""
    from app.models.sync_job import SYNC_KIND_BREVO
    from app.services import sync_jobs

    def work(job_id):
        return run(dry_run=dry_run, entity_ids=entity_ids, progress=sync_jobs.progress_callback(job_id, throttle=1))
    label = "Aperçu de la synchronisation Brevo…" if dry_run else "Synchronisation des adhérents avec Brevo…"
    return sync_jobs.start(app, SYNC_KIND_BREVO, work, message=label,
                           error_message=lambda exc: getattr(exc, "message", None) or str(exc))
