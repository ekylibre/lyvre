"""Outils d'agent en écriture : brouillons seulement (lot AK3, claudedocs/design_api_mcp_aiffel.md § 7.2 à 7.5).

Rien n'est comptabilisé, validé, numéroté ni envoyé :
- facture d'achat créée sans comptabilisation, « à vérifier » tant qu'un humain ne l'a pas marquée vérifiée (D3) ;
- tiers créé « à vérifier » ;
- écriture créée **non validée** (brouillard), comme une saisie manuelle (D4).
Idempotence : une `external_ref` déjà connue (référence Fourmy…) ou une `idempotency_key` déjà reçue de la clé renvoie
l'objet existant sans rien écrire. Les handlers lisent la clé dans `g.api_key` ; le commit et le journal sont faits par
`agent_tools.run`.
"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime

from flask import g

from app.extensions import db
from app.services.assistant.tools import euros

EXTERNAL_REF_MAX = 120
IDEMPOTENCY_MAX = 80
KNOWN_RATES_BP = (2000, 1000, 850, 550, 210, 0)


def _origin(args: dict) -> dict:
    key = g.api_key
    return {"key_id": key.id, "label": key.name, "external_ref": _external_ref(args)}


def _external_ref(args: dict) -> str | None:
    ref = str(args.get("external_ref") or "").strip()
    return ref[:EXTERNAL_REF_MAX] or None


def _object(kind: str, obj_id: int) -> dict:
    return {"type": kind, "id": obj_id}


def previous(args: dict, model, kind: str):
    """Objet déjà créé pour cette référence externe ou cette clé d'idempotence, sinon None."""
    from app.models import ApiCall
    ref = _external_ref(args)
    if ref:
        found = model.query.filter_by(external_ref=ref).first()
        if found is not None:
            return found
    idem = str(args.get("idempotency_key") or "").strip()[:IDEMPOTENCY_MAX]
    if idem:
        call = ApiCall.query.filter_by(key_id=g.api_key.id, idempotency_key=idem, object_type=kind).first()
        if call is not None and call.object_id:
            return db.session.get(model, call.object_id)
    return None


def _amount(value) -> str | None:
    """Montant de l'agent (nombre ou texte « 1 200,50 », « 1200.50 », « 1 200 € ») → texte du formulaire."""
    if value is None or value == "":
        return None
    text = str(value).replace("€", "").replace(" ", " ").replace("\xa0", " ").strip()
    return text


def _decode_file(args: dict) -> str | None:
    """Pièce de l'appel → jeton de pièce en attente (ou None). ValueError si elle est illisible."""
    from app.services import attachments
    from app.services.attachments import AttachmentError
    token = str(args.get("file_token") or "").strip()
    if token:
        try:
            attachments.staged(token)
        except AttachmentError as exc:
            raise ValueError(str(exc)) from None
        return token
    file = args.get("file")
    if not file:
        return None
    if not isinstance(file, dict) or not file.get("content_base64"):
        raise ValueError("Pièce : objet {name, content_base64} attendu.")
    try:
        body = base64.b64decode(str(file["content_base64"]), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Pièce : contenu base64 invalide.") from None
    try:
        return attachments.stage_bytes(body, str(file.get("name") or "piece"))
    except AttachmentError as exc:
        raise ValueError(str(exc)) from None


def _rate(untaxed: int | None, tax: int | None) -> int | None:
    """Taux de TVA déduit de HT et TVA, s'il correspond à un taux connu (à 0,1 point près)."""
    if not untaxed or tax is None:
        return None
    rate = tax * 10000 / untaxed
    return next((r for r in KNOWN_RATES_BP if abs(rate - r) <= 10), None)


# ------------------------------------------------------------------ fournisseur


def _find_party(supplier: dict):
    from app.models import Entity
    from app.services import purchase_sync
    if supplier.get("party_id"):
        entity = db.session.get(Entity, int(supplier["party_id"])) if str(supplier["party_id"]).isdigit() else None
        if entity is None:
            raise ValueError("Tiers introuvable (party_id).")
        return entity
    siren = "".join(ch for ch in str(supplier.get("siren") or "") if ch.isdigit())
    if len(siren) == 9:
        entity = Entity.query.filter_by(siren=siren).first()
        if entity is not None:
            return entity
    if any(supplier.get(k) for k in ("vat_number", "siret", "name")):
        return purchase_sync.find_supplier(None, supplier.get("vat_number"), supplier.get("siret"), None,
                                           supplier.get("name"))
    return None


def _sirene(number: str) -> dict:
    """Fiche Sirene d'un SIREN ou SIRET (vide si le service est indisponible)."""
    from app.services import sirene
    try:
        if not sirene.available():
            return {}
        found = sirene.search(number)
    except Exception:  # noqa: BLE001 — la création se fait sans Sirene
        return {}
    return found[0] if found else {}


def new_supplier(name: str, ids: dict, origin: dict):
    """Fournisseur créé « à vérifier » (sans commit)."""
    from app.models import Entity
    from app.services import purchase_entry, purchase_sync
    entity = Entity(name=name[:200], entity_type="FOURNISSEUR", origin_key_id=origin["key_id"],
                    origin_label=origin["label"][:80], external_ref=ids.get("external_ref"))
    number = ids.get("siret") or ids.get("siren")
    info = _sirene(number) if number else {}
    for key, value in purchase_entry.clean_new_entity(info).items():
        setattr(entity, key, value)
    entity.siren = entity.siren or (ids.get("siren") if len(ids.get("siren") or "") == 9 else None)
    entity.siret = purchase_sync.normalize_siret(ids.get("siret")) or (info.get("siret") if info else None)
    entity.vat_number = purchase_sync.normalize_vat(ids.get("vat_number"))
    entity.email = (ids.get("email") or "").strip()[:200] or None
    db.session.add(entity)
    db.session.flush()
    return entity


def _party_payload(entity, created: bool) -> dict:
    from app.services.agent_tools import link
    return {"created": created, "party_id": entity.id, "name": entity.name, "siren": entity.siren,
            "vat_number": entity.vat_number, "state": "à vérifier" if entity.origin_key_id and not entity.checked_at
            else "vérifié", "url": link(f"/entities/{entity.id}"), "object": _object("entity", entity.id)}


def create_supplier(args: dict) -> dict:
    from app.models import Entity
    from app.services.counterparties import name_key
    existing = previous(args, Entity, "entity")
    if existing is not None:
        return _party_payload(existing, False)
    name = str(args.get("name") or "").strip()
    if not name:
        return {"error": "Nom du fournisseur obligatoire."}
    ids = {k: str(args.get(k) or "").strip() for k in ("siren", "siret", "vat_number", "email")}
    found = _find_party({**ids, "name": None}) if any(ids[k] for k in ("siren", "siret", "vat_number")) else None
    if found is None:
        key = name_key(name)
        found = next((e for e in Entity.query.order_by(Entity.id) if name_key(e.name) == key), None)
    if found is not None:
        return {**_party_payload(found, False), "message": "Tiers déjà connu : rien n'a été créé."}
    entity = new_supplier(name, {**ids, "external_ref": _external_ref(args)}, _origin(args))
    return _party_payload(entity, True)


# ------------------------------------------------------------------ facture d'achat


def _purchase_payload(p, created: bool, warnings=None) -> dict:
    from app.services import purchase_posting
    from app.services.agent_tools import link
    state = purchase_posting.purchase_state(p)
    return {"created": created, "purchase_id": p.id, "supplier": {"id": p.entity_id, "name": p.entity.name if p.entity
                                                                  else p.supplier_name},
            "invoice_number": p.invoice_number, "issue_date": p.issue_date.isoformat() if p.issue_date else None,
            "total": euros(p.total_cents), "has_attachment": bool(p.attachment_path),
            "state": "comptabilisée" if state.code == "posted" else "à vérifier dans Lyvre", "reasons": state.reasons,
            "warnings": warnings or [], "url": link(f"/purchases/{p.id}"), "object": _object("purchase", p.id),
            "message": "Brouillon enregistré dans Lyvre, NON comptabilisé : l'utilisateur le vérifie et le valide."}


def _rows_from_args(lines: list) -> list[dict]:
    rows = []
    for i, line in enumerate(lines):
        if not isinstance(line, dict):
            raise ValueError(f"Ligne {i + 1} : objet attendu.")
        untaxed = _amount(line.get("amount_untaxed"))
        rate = line.get("vat_rate")
        rows.append({"label": str(line.get("label") or "")[:300], "untaxed": untaxed,
                     "vat_rate": "" if rate in (None, "") else str(rate).replace("%", "").strip(),
                     "vat": _amount(line.get("vat")) or "", "account_code": str(line.get("account") or "").strip(),
                     "product_id": "", "project_id": "", "analytic": ""})
    return rows


def create_purchase_draft(args: dict) -> dict:
    from app.models import Purchase
    from app.services import purchase_entry, purchase_posting
    existing = previous(args, Purchase, "purchase")
    if existing is not None:
        return _purchase_payload(existing, False)
    try:
        token = _decode_file(args)
    except ValueError as exc:
        return {"error": str(exc)}
    values, rows, warnings = {}, [], []
    if token:
        form = purchase_entry.form_from_extraction(purchase_entry.read_staged(token))
        values.update(form.values)
        rows, warnings = list(form.rows), list(form.warnings)
    for key in ("issue_date", "due_date", "invoice_number"):
        if args.get(key):
            values[key] = str(args[key]).strip()
    amounts_given = False
    for key in ("total", "untaxed", "tax"):
        if args.get(key) not in (None, ""):
            values[key] = _amount(args[key])
            amounts_given = True
    if args.get("is_credit_note") is not None:
        values["is_credit_note"] = bool(args.get("is_credit_note"))

    supplier = args.get("supplier") or {}
    if not isinstance(supplier, dict):
        return {"error": "supplier : objet {name, siren, siret, vat_number, party_id} attendu."}
    try:
        entity = _find_party(supplier) if supplier else None
    except ValueError as exc:
        return {"error": str(exc)}
    name = str(supplier.get("name") or "").strip() or values.get("new_name") or values.get("supplier_name")
    if supplier.get("vat_number"):
        values["supplier_vat"] = supplier["vat_number"]
    if supplier.get("siret"):
        values["supplier_siret"] = supplier["siret"]
    origin = _origin(args)
    created_supplier = False
    if entity is None and values.get("entity_id") and values["entity_id"] != "new":
        from app.models import Entity
        entity = db.session.get(Entity, int(values["entity_id"]))
    if entity is None and name and "parties" in g.api_key.writes:
        ids = {"siren": str(supplier.get("siren") or ""), "siret": str(supplier.get("siret") or ""),
               "vat_number": str(supplier.get("vat_number") or values.get("supplier_vat") or ""), "email": ""}
        entity, created_supplier = new_supplier(name, ids, {**origin, "external_ref": None}), True
    if entity is not None:
        values["entity_id"], values["supplier_name"] = str(entity.id), entity.name
    else:
        values["entity_id"], values["supplier_name"] = "", name or None
        warnings.append("Fournisseur non rattaché : à choisir dans Lyvre.")

    clean, errors = purchase_entry.validate_header(values)
    if errors:
        db.session.rollback()
        return {"error": " ".join(errors)}
    if args.get("lines"):
        try:
            rows = _rows_from_args(args["lines"])
        except ValueError as exc:
            db.session.rollback()
            return {"error": str(exc)}
    elif amounts_given or not rows:
        rate = _rate(clean["untaxed_cents"], clean["tax_cents"])
        taxes = [(rate, clean["untaxed_cents"], clean["tax_cents"])] if rate is not None else []
        rows = purchase_entry.line_rows(purchase_entry.proposed_lines(entity, clean["total_cents"],
                                                                      clean["untaxed_cents"], taxes))
    notes = []
    if args.get("note"):
        notes.append(f"Note de « {origin['label']} » : {str(args['note']).strip()[:500]}")
    dups = purchase_entry.duplicates(entity.id if entity else None, clean["invoice_number"], clean["issue_date"],
                                     clean["total_cents"], supplier_name=clean["supplier_name"])
    if dups:
        notes.append("Doublon possible : " + ", ".join(f"facture n° {d.invoice_number or d.id} du "
                                                         f"{d.issue_date:%d/%m/%Y}" if d.issue_date else str(d.id)
                                                         for d in dups[:3]) + ".")
        warnings.append(notes[-1])
    p, _outcome = purchase_entry.create(clean, rows, token, post=False, origin=origin)
    if notes:
        p.review_reason = " ".join(notes)
    if created_supplier:
        warnings.append(f"Fournisseur « {entity.name} » créé, à vérifier.")
    assert purchase_posting.purchase_state(p).code != "posted"
    return _purchase_payload(p, True, warnings)


def attach_document(args: dict) -> dict:
    from app.models import Purchase
    from app.services import attachments
    p = db.session.get(Purchase, int(args["purchase_id"])) if str(args.get("purchase_id") or "").isdigit() else None
    if p is None:
        return {"error": "Facture d'achat introuvable."}
    if p.origin_key_id != g.api_key.id or p.checked_at is not None or p.journal_entry_id is not None:
        return {"error": "Seule une facture saisie par cette clé et pas encore vérifiée reçoit une pièce par cet outil."}
    try:
        token = _decode_file(args)
    except ValueError as exc:
        return {"error": str(exc)}
    if token is None:
        return {"error": "Pièce attendue (file ou file_token)."}
    attachments.store(p, token)
    return {**_purchase_payload(p, False), "attached": True}


# ------------------------------------------------------------------ écriture en brouillard


def create_entry_draft(args: dict) -> dict:
    from app.models import Account, FiscalYear, Journal, JournalEntry
    from app.services.agent_tools import link
    from app.services.ledger import LedgerError, post_entry, validate_entry_payload
    from app.services.assistant.tools import _cents_from
    existing = previous(args, JournalEntry, "journal_entry")
    if existing is not None:
        return {"created": False, "entry_id": existing.id, "url": link(f"/entries/{existing.id}"),
                "object": _object("journal_entry", existing.id)}
    try:
        day = datetime.fromisoformat(str(args.get("date") or "")).date()
    except ValueError:
        return {"error": "Date attendue au format AAAA-MM-JJ."}
    fy = FiscalYear.query.filter(FiscalYear.start_date <= day, FiscalYear.end_date >= day).first()
    if fy is None or fy.closed:
        return {"error": f"Aucun exercice ouvert au {day:%d/%m/%Y}."}
    journal = Journal.query.filter_by(code=(args.get("journal") or "OD").strip().upper()).first()
    if journal is None:
        return {"error": "Journal inconnu (codes : " + ", ".join(j.code for j in Journal.query.order_by(Journal.code)) + ")."}
    lines = []
    for i, raw in enumerate(args.get("lines") or []):
        account = Account.query.filter_by(code=str(raw.get("account") or "").strip()).first()
        if account is None or account.is_header:
            return {"error": f"Ligne {i + 1} : compte « {raw.get('account')} » inconnu ou d'en-tête."}
        try:
            debit, credit = _cents_from(raw.get("debit"), f"Ligne {i + 1}"), _cents_from(raw.get("credit"), f"Ligne {i + 1}")
        except ValueError as exc:
            return {"error": str(exc)}
        if bool(debit) == bool(credit):
            return {"error": f"Ligne {i + 1} : un débit ou un crédit, pas les deux."}
        lines.append({"account_id": account.id, "label": str(raw.get("label") or "")[:300], "debit_cents": debit,
                      "credit_cents": credit})
    clean, errors = validate_entry_payload({"fiscal_year_id": fy.id, "journal_id": journal.id,
                                            "entry_date": day.isoformat(),
                                            "description": str(args.get("label") or "")[:500], "lines": lines})
    if errors:
        return {"error": " ".join(dict.fromkeys(str(v) for v in errors.values()))}
    origin = _origin(args)
    try:
        entry = post_entry(clean["fiscal_year"].id, clean["journal"].id, clean["entry_date"], clean["description"],
                           clean["lines"], commit=False)
    except LedgerError as exc:
        db.session.rollback()
        return {"error": str(exc)}
    entry.origin_key_id, entry.origin_label, entry.external_ref = origin["key_id"], origin["label"][:80], origin["external_ref"]
    total = sum(line["debit_cents"] for line in lines)
    return {"created": True, "entry_id": entry.id, "date": day.isoformat(), "journal": journal.code,
            "amount": euros(total), "validated": False, "url": link(f"/entries/{entry.id}"),
            "object": _object("journal_entry", entry.id),
            "message": "Écriture enregistrée en brouillard (non validée) : l'utilisateur la vérifie et la valide."}
