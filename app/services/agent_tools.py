"""Outils d'agent par domaine (lot AK2, claudedocs/design_api_mcp_aiffel.md § 7).

Un seul registre pour le serveur MCP (`/mcp`, `tools/call`) et le REST (`POST /api/v1/agent/tools/<outil>`) :
- lecture : les outils de l'assistant Claude (`assistant/tools.py`, mêmes handlers et schémas) rangés par domaine,
  et des outils propres à l'agent (achats, banque, ventes, tiers, immobilisations) ;
- écriture (lot AK3) : brouillons seulement.
Chaque appel est contrôlé : outil du registre, domaine accordé à la clé, arguments conformes au schéma.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Callable

from app.services.assistant import tools as assistant_tools
from app.services.assistant.tools import _schema, euros

ALWAYS = "*"        # outil permis à toute clé valide (contexte, calculettes : rien de sensible du dossier)
MAX_RESULT_CHARS = assistant_tools.MAX_RESULT_CHARS
MAX_ROWS = 50


@dataclass(frozen=True)
class AgentTool:
    name: str
    title: str
    domain: str
    description: str
    schema: dict
    handler: Callable[[dict], dict]
    access: str = "read"          # read | write

    def definition(self) -> dict:
        """Définition MCP (`tools/list`)."""
        return {"name": self.name, "title": self.title, "description": self.description, "inputSchema": self.schema,
                "annotations": {"title": self.title, "readOnlyHint": self.access == "read",
                                "destructiveHint": False, "openWorldHint": False}}


# ------------------------------------------------------------------ liens


def link(path: str) -> str:
    """Adresse absolue d'un écran de Lyvre (APP_BASE_URL), ou le chemin seul si elle n'est pas configurée."""
    from flask import current_app
    base = (current_app.config.get("APP_BASE_URL") or "").rstrip("/")
    return f"{base}{path}"


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _date_arg(args: dict, key: str) -> date | None:
    value = args.get(key)
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValueError(f"{key} : date attendue au format AAAA-MM-JJ.") from None


def _limit(args: dict) -> int:
    try:
        return max(1, min(int(args.get("limit") or 20), MAX_ROWS))
    except (TypeError, ValueError):
        return 20


# ------------------------------------------------------------------ achats


def _purchase_row(p) -> dict:
    from app.services import purchase_posting, purchase_settlement
    state = purchase_posting.purchase_state(p)
    return {"id": p.id, "supplier": p.entity.name if p.entity else p.supplier_name, "number": p.invoice_number,
            "issue_date": _iso(p.issue_date), "due_date": _iso(p.due_date), "credit_note": p.is_credit_note,
            "total": euros(p.total_cents), "remaining": euros(purchase_settlement.remaining_cents(p)),
            "state": {"posted": "comptabilisée", "hidden": "masquée", "ready": "prête",
                      "to_complete": "à compléter"}.get(state.code, state.code),
            "url": link(f"/purchases/{p.id}")}


def list_purchases(args: dict) -> dict:
    from app.models import Purchase
    from app.services import purchase_settlement
    try:
        start, end = _date_arg(args, "date_from"), _date_arg(args, "date_to")
    except ValueError as exc:
        return {"error": str(exc)}
    query = Purchase.query.filter(Purchase.is_hidden.is_(False))
    if start:
        query = query.filter(Purchase.issue_date >= start)
    if end:
        query = query.filter(Purchase.issue_date <= end)
    supplier = (args.get("supplier") or "").strip()
    if supplier:
        query = query.filter(Purchase.supplier_name.ilike(f"%{supplier[:80]}%"))
    status = args.get("status") or "all"
    rows = query.order_by(Purchase.issue_date.desc().nullslast(), Purchase.id.desc()).limit(500).all()
    today = date.today()
    if status in ("unpaid", "overdue"):
        rows = [p for p in rows if purchase_settlement.remaining_cents(p) > 0 and not p.is_credit_note]
    if status == "overdue":
        rows = [p for p in rows if p.due_date and p.due_date < today]
    if status == "to_complete":
        rows = [p for p in rows if p.journal_entry_id is None]
    limit = _limit(args)
    total_remaining = sum(purchase_settlement.remaining_cents(p) for p in rows) if status in ("unpaid", "overdue") else None
    return {"purchases": [_purchase_row(p) for p in rows[:limit]], "count": len(rows), "more": len(rows) > limit,
            "total_remaining": euros(total_remaining) if total_remaining is not None else None}


def get_purchase(args: dict) -> dict:
    from app.extensions import db
    from app.models import Purchase
    p = db.session.get(Purchase, int(args.get("id") or 0)) if str(args.get("id") or "").isdigit() else None
    if p is None:
        return {"error": "Facture d'achat introuvable."}
    from app.services import purchase_posting
    row = _purchase_row(p)
    row.update({"untaxed": euros(p.untaxed_cents), "tax": euros(p.tax_cents), "source": p.source,
                "reasons": purchase_posting.purchase_state(p).reasons, "has_attachment": bool(p.attachment_path),
                "lines": [{"label": line.label, "account": line.account.code if line.account else None,
                           "untaxed": euros(line.untaxed_cents), "vat_rate_percent": line.vat_rate_bp / 100
                           if line.vat_rate_bp is not None else None, "vat": euros(line.vat_cents),
                           "total": euros(line.total_cents)} for line in p.lines],
                "payments": [{"date": _iso(pay.bank_transaction.transaction_date) if pay.bank_transaction else None,
                              "amount": euros(abs(pay.bank_transaction.amount_cents)) if pay.bank_transaction else None,
                              "origin": pay.origin} for pay in p.payments]})
    return row


# ------------------------------------------------------------------ banque


def get_bank_accounts(_args: dict) -> dict:
    from app.extensions import db
    from app.models import BankAccount, BankTransaction
    from app.services import cash
    today = date.today()
    out = []
    for ba in BankAccount.query.order_by(BankAccount.label).all():
        last = db.session.query(db.func.max(BankTransaction.transaction_date)).filter(
            BankTransaction.bank_account_id == ba.id).scalar()
        out.append({"id": ba.id, "label": ba.label, "kind": ba.kind,
                    "ledger_balance": euros(cash.ledger_balance(ba.account_id, today)) if ba.account_id else None,
                    "last_transaction": _iso(last),
                    "unreconciled": BankTransaction.query.filter_by(bank_account_id=ba.id, reconciled=False).count()})
    return {"today": today.isoformat(), "bank_accounts": out,
            "note": "Solde comptable au jour (écritures saisies), hors à-nouveaux."}


def list_bank_transactions(args: dict) -> dict:
    from app.models import BankTransaction
    try:
        start, end = _date_arg(args, "date_from"), _date_arg(args, "date_to")
    except ValueError as exc:
        return {"error": str(exc)}
    query = BankTransaction.query.filter(BankTransaction.is_reversed.is_(False))
    if str(args.get("bank_account_id") or "").isdigit():
        query = query.filter(BankTransaction.bank_account_id == int(args["bank_account_id"]))
    if start:
        query = query.filter(BankTransaction.transaction_date >= start)
    if end:
        query = query.filter(BankTransaction.transaction_date <= end)
    text = (args.get("text") or "").strip()
    if text:
        like = f"%{text[:80]}%"
        query = query.filter(BankTransaction.label.ilike(like) | BankTransaction.counterparty.ilike(like))
    if args.get("unreconciled_only"):
        query = query.filter(BankTransaction.reconciled.is_(False))
    limit = _limit(args)
    rows = query.order_by(BankTransaction.transaction_date.desc(), BankTransaction.id.desc()).limit(limit + 1).all()
    return {"transactions": [{"id": t.id, "date": _iso(t.transaction_date), "label": t.label,
                              "counterparty": t.counterparty, "amount": euros(t.amount_cents),
                              "reconciled": t.reconciled, "bank_account": t.bank_account.label}
                             for t in rows[:limit]], "more": len(rows) > limit}


# ------------------------------------------------------------------ ventes


def list_sales(args: dict) -> dict:
    from app.models import Sale
    try:
        start, end = _date_arg(args, "date_from"), _date_arg(args, "date_to")
    except ValueError as exc:
        return {"error": str(exc)}
    query = Sale.query
    kind = args.get("kind")
    if kind in ("quote", "invoice", "credit_note"):
        query = query.filter(Sale.kind == kind)
    if start:
        query = query.filter(Sale.issue_date >= start)
    if end:
        query = query.filter(Sale.issue_date <= end)
    rows = query.order_by(Sale.issue_date.desc().nullslast(), Sale.id.desc()).limit(500).all()
    if args.get("unpaid_only"):
        rows = [s for s in rows if s.kind == "invoice" and s.status != "draft" and (s.total_cents or 0) > (s.paid_cents or 0)]
    limit = _limit(args)
    return {"sales": [{"id": s.id, "kind": s.kind, "status": s.status, "number": s.number,
                       "client": s.entity.name if s.entity else None, "issue_date": _iso(s.issue_date),
                       "due_date": _iso(s.due_date), "total": euros(s.total_cents), "paid": euros(s.paid_cents),
                       "url": link(f"/sales/{s.id}")} for s in rows[:limit]],
            "count": len(rows), "more": len(rows) > limit}


# ------------------------------------------------------------------ tiers


def find_party(args: dict) -> dict:
    from app.models import Entity
    from app.services import purchase_sync
    text = (args.get("query") or "").strip()
    if len(text) < 2:
        return {"error": "Texte recherché : 2 caractères au moins (nom, SIREN, SIRET, numéro de TVA ou e-mail)."}
    digits = text.replace(" ", "")
    query = Entity.query
    if digits.isdigit() and len(digits) in (9, 14):
        query = query.filter((Entity.siren == digits[:9]) | (Entity.siret == digits))
    else:
        vat = purchase_sync.normalize_vat(text)
        like = f"%{text[:80]}%"
        query = query.filter(Entity.name.ilike(like) | Entity.email.ilike(like) | (Entity.vat_number == vat))
    rows = query.order_by(Entity.name).limit(21).all()
    return {"parties": [{"id": e.id, "name": e.name, "type": e.entity_type, "siren": e.siren, "siret": e.siret,
                         "vat_number": e.vat_number, "account": e.account_code, "customer_account": e.customer_account_code,
                         "city": e.city, "url": link(f"/entities/{e.id}")} for e in rows[:20]],
            "more": len(rows) > 20}


# ------------------------------------------------------------------ immobilisations


def list_assets(args: dict) -> dict:
    from app.models import Asset
    query = Asset.query.filter(Asset.parent_id.is_(None))
    if not args.get("include_disposed"):
        query = query.filter(Asset.disposal_date.is_(None))
    rows = query.order_by(Asset.acquired_on.desc()).limit(201).all()
    return {"assets": [{"id": a.id, "label": a.label, "acquired_on": _iso(a.acquired_on),
                        "in_service": _iso(a.in_service_date), "acquisition": euros(a.acquisition_cents),
                        "method": a.method, "duration_months": a.duration_months, "status": a.status,
                        "disposed_on": _iso(a.disposal_date), "url": link(f"/assets/{a.id}")} for a in rows[:200]],
            "more": len(rows) > 200}


# ------------------------------------------------------------------ registre

_PERIOD = {"date_from": {"type": "string", "description": "Début, AAAA-MM-JJ (facultatif)"},
           "date_to": {"type": "string", "description": "Fin, AAAA-MM-JJ (facultatif)"}}
_LIMIT = {"limit": {"type": "integer", "description": f"Nombre de lignes (défaut 20, au plus {MAX_ROWS})"}}

# Outils de l'assistant repris (lecture) : nom → (domaine, titre).
_ASSISTANT = {
    "get_context": (ALWAYS, "Dossier de la structure"),
    "list_calculators": (ALWAYS, "Calculettes disponibles"),
    "run_calculator": (ALWAYS, "Calculette"),
    "get_agenda": ("agenda", "Échéancier"),
    "get_deadline_fiche": ("agenda", "Fiche d'échéance"),
    "get_balances": ("accounting", "Soldes des comptes"),
    "search_entries": ("accounting", "Recherche d'écritures"),
    "get_closing_checks": ("accounting", "Contrôles de clôture"),
    "get_vat": ("tax", "Déclarations de TVA"),
    "get_tax_result": ("tax", "Résultat fiscal"),
    "get_msa": ("tax", "Cotisations MSA"),
    "get_parameter": ("tax", "Paramètre réglementaire"),
    "get_margins": ("agronomy", "Marges par activité"),
    "get_aids": ("agronomy", "Aides et subventions"),
}


def _run_calculator(args: dict) -> dict:
    """Calculette pour une clé : le préremplissage lit la comptabilité (immobilisations, baux, DEP, TVA, achats…),
    il demande donc le domaine Comptabilité en lecture (revue de sécurité AK4)."""
    from flask import g
    key = getattr(g, "api_key", None)
    if args.get("prefill") and (key is None or "accounting" not in key.reads):
        return {"error": "Préremplissage réservé à une clé qui lit la Comptabilité : passez les valeurs dans « values »."}
    return assistant_tools.run_calculator(args)


_HANDLER_OVERRIDES = {"run_calculator": _run_calculator}


def _from_assistant() -> list[AgentTool]:
    by_name = {t.name: t for t in assistant_tools.TOOLS}
    return [AgentTool(name, title, domain, by_name[name].description, by_name[name].schema,
                      _HANDLER_OVERRIDES.get(name, by_name[name].handler))
            for name, (domain, title) in _ASSISTANT.items()]


OWN_TOOLS: tuple[AgentTool, ...] = (
    AgentTool("list_purchases", "Factures d'achat", "purchases",
              "Factures d'achat, plus récentes d'abord : fournisseur, dates, TTC, restant à payer, état (comptabilisée, "
              "prête, à compléter) et lien. Filtre status : all, unpaid (à payer), overdue (échues), to_complete.",
              _schema({"status": {"type": "string", "enum": ["all", "unpaid", "overdue", "to_complete"]},
                       "supplier": {"type": "string", "description": "Nom du fournisseur (partie du nom)"},
                       **_PERIOD, **_LIMIT}), list_purchases),
    AgentTool("get_purchase", "Facture d'achat", "purchases",
              "Une facture d'achat : lignes (compte, HT, TVA), règlements, motifs si elle est à compléter, lien.",
              _schema({"id": {"type": "integer", "description": "Identifiant (list_purchases)"}}, ["id"]), get_purchase),
    AgentTool("get_bank_accounts", "Comptes bancaires", "bank",
              "Comptes bancaires : solde comptable au jour, date de la dernière transaction, transactions non rapprochées.",
              _schema(), get_bank_accounts),
    AgentTool("list_bank_transactions", "Transactions bancaires", "bank",
              "Transactions bancaires, plus récentes d'abord, filtrées par compte, période, texte ou non rapprochées.",
              _schema({"bank_account_id": {"type": "integer"}, "text": {"type": "string"},
                       "unreconciled_only": {"type": "boolean"}, **_PERIOD, **_LIMIT}), list_bank_transactions),
    AgentTool("list_sales", "Pièces de vente", "sales",
              "Devis, factures et avoirs de vente : numéro, client, dates, TTC, encaissé, statut, lien.",
              _schema({"kind": {"type": "string", "enum": ["quote", "invoice", "credit_note"]},
                       "unpaid_only": {"type": "boolean", "description": "Factures émises non soldées"},
                       **_PERIOD, **_LIMIT}), list_sales),
    AgentTool("find_party", "Recherche de tiers", "parties",
              "Fournisseurs, clients et adhérents par nom, SIREN, SIRET, numéro de TVA ou e-mail (20 au plus).",
              _schema({"query": {"type": "string"}}, ["query"]), find_party),
    AgentTool("list_assets", "Immobilisations", "assets",
              "Immobilisations en service (ou toutes) : acquisition, mise en service, valeur, méthode, durée.",
              _schema({"include_disposed": {"type": "boolean"}}), list_assets),
)


def _write_tools() -> tuple[AgentTool, ...]:
    from app.services import agent_writes as w
    ref = {"external_ref": {"type": "string", "description": "Référence externe stable (ex. « fourmy:intervention/123 ») : "
                            "une seconde création avec la même référence renvoie l'objet existant"},
           "idempotency_key": {"type": "string", "description": "Clé d'idempotence (réessai sans doublon)"}}
    file_props = {"file": {"type": "object", "description": "Pièce (photo JPEG/PNG ou PDF, 10 Mo au plus)",
                           "properties": {"name": {"type": "string"}, "content_base64": {"type": "string"}},
                           "required": ["content_base64"]},
                  "file_token": {"type": "string", "description": "Jeton d'une pièce déposée par POST /api/v1/agent/files"}}
    supplier = {"type": "object", "description": "Fournisseur : party_id (find_party) ou nom et identifiants",
                "properties": {"party_id": {"type": "integer"}, "name": {"type": "string"}, "siren": {"type": "string"},
                               "siret": {"type": "string"}, "vat_number": {"type": "string"}}}
    amount = {"type": ["string", "number"]}
    return (
        AgentTool("create_purchase_draft", "Saisir une facture d'achat (brouillon)", "purchases",
                  "Crée une facture d'achat en BROUILLON à vérifier dans Lyvre (jamais comptabilisée par cet outil). "
                  "Une dépense sans facture (ticket, frais) passe aussi par ici, le ticket en pièce. Avec une pièce, "
                  "Lyvre la lit (Factur-X, OCR) et complète ce qui manque ; les arguments l'emportent. Montants en "
                  "euros (« 1 200,50 » ou 1200.5). Renvoie le lien vers la facture.",
                  _schema({"supplier": supplier, "issue_date": {"type": "string", "description": "AAAA-MM-JJ"},
                           "due_date": {"type": "string"}, "invoice_number": {"type": "string"},
                           "total": {**amount, "description": "TTC"}, "untaxed": {**amount, "description": "HT"},
                           "tax": {**amount, "description": "TVA"}, "is_credit_note": {"type": "boolean"},
                           "lines": {"type": "array", "items": {"type": "object", "properties": {
                               "label": {"type": "string"}, "amount_untaxed": amount, "vat_rate": amount,
                               "vat": amount, "account": {"type": "string", "description": "Compte de charge 6…"}}}},
                           "note": {"type": "string", "description": "Remarque pour la personne qui vérifie"},
                           **file_props, **ref}),
                  w.create_purchase_draft, access="write"),
        AgentTool("attach_document", "Joindre une pièce à une facture d'achat", "purchases",
                  "Joint une pièce à une facture d'achat saisie par cette clé et pas encore vérifiée.",
                  _schema({"purchase_id": {"type": "integer"}, **file_props}, ["purchase_id"]),
                  w.attach_document, access="write"),
        AgentTool("create_supplier", "Créer un fournisseur", "parties",
                  "Crée un fournisseur « à vérifier » s'il est introuvable (fiche complétée par Sirene si le SIREN ou "
                  "le SIRET est donné) ; renvoie le tiers existant s'il est déjà connu.",
                  _schema({"name": {"type": "string"}, "siren": {"type": "string"}, "siret": {"type": "string"},
                           "vat_number": {"type": "string"}, "email": {"type": "string"}, **ref}, ["name"]),
                  w.create_supplier, access="write"),
        AgentTool("create_entry_draft", "Saisir une écriture (brouillard)", "accounting",
                  "Enregistre une écriture équilibrée NON VALIDÉE (brouillard), que l'utilisateur vérifie et valide. "
                  "Montants en euros (« 1234,56 »).",
                  _schema({"date": {"type": "string", "description": "AAAA-MM-JJ"},
                           "journal": {"type": "string", "description": "Code du journal (OD par défaut)"},
                           "label": {"type": "string"},
                           "lines": {"type": "array", "items": {"type": "object", "properties": {
                               "account": {"type": "string"}, "label": {"type": "string"},
                               "debit": {"type": "string"}, "credit": {"type": "string"}}, "required": ["account"]}},
                           **ref}, ["date", "lines"]),
                  w.create_entry_draft, access="write"),
    )


def registry() -> list[AgentTool]:
    return sorted([*_from_assistant(), *OWN_TOOLS, *_write_tools()], key=lambda t: t.name)


def allowed(tool: AgentTool, key) -> bool:
    if tool.domain == ALWAYS:
        return True
    return tool.domain in (key.writes if tool.access == "write" else key.reads)


def for_key(key) -> list[AgentTool]:
    return [t for t in registry() if allowed(t, key)]


class ToolRefused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def find(name: str, key) -> AgentTool:
    from app.services import api_domains
    tool = next((t for t in registry() if t.name == name), None)
    if tool is None:
        raise ToolRefused("unknown_tool", f"Outil inconnu : {name}.")
    if not allowed(tool, key):
        verb = "en écriture" if tool.access == "write" else "en lecture"
        raise ToolRefused("domain_forbidden", f"Domaine « {api_domains.label(tool.domain)} » non accordé {verb} "
                          f"à la clé « {key.name} ».")
    return tool


def _conforms(schema: dict, args: dict) -> bool:
    props = schema.get("properties", {})
    if set(args) - set(props) or any(k not in args for k in schema.get("required", [])):
        return False
    for key, value in args.items():
        declared = props[key].get("type")
        kinds = declared if isinstance(declared, list) else [declared]
        if value is None:
            if "null" not in kinds:
                return False
            continue
        if not any(_is_kind(value, kind) for kind in kinds):
            return False
        if "enum" in props[key] and value not in props[key]["enum"]:
            return False
    return True


def _is_kind(value, kind) -> bool:
    if kind is None:
        return True
    if isinstance(value, bool):
        return kind == "boolean"
    if kind == "integer":
        return isinstance(value, int) or (isinstance(value, str) and value.isdigit())
    if kind == "number":
        return isinstance(value, (int, float))
    expected = {"string": str, "array": list, "boolean": bool, "object": dict}
    return isinstance(value, expected[kind]) if kind in expected else True


def _log(tool_name: str, key, channel: str, started: float, *, tool: AgentTool | None = None, args=None,
         result=None, error=False, status=None) -> None:
    """Inscrit l'appel d'outil au journal (lot AK4) : objet créé et clé d'idempotence pour une écriture."""
    import time
    from app.services import api_journal
    obj = result.get("object") if isinstance(result, dict) and (result.get("created") or result.get("attached")) else None
    idem = (str((args or {}).get("idempotency_key") or "").strip()[:80] or None) if obj else None
    message = result.get("error") if isinstance(result, dict) and error else None
    api_journal.record(key.id, channel, tool_name, domain=tool.domain if tool and tool.domain != ALWAYS else None,
                       access=tool.access if tool else None, status=status or (422 if error else 200), error=message,
                       object_type=obj["type"] if obj else None, object_id=obj["id"] if obj else None,
                       idempotency_key=idem, duration_ms=int((time.monotonic() - started) * 1000))


def run(name: str, args, key, channel: str = "mcp") -> tuple[dict, bool]:
    """(résultat, erreur ?). Lève ToolRefused si l'outil est inconnu, hors des domaines de la clé ou si le plafond
    quotidien de créations est atteint. Une lecture est toujours annulée (rollback) ; une écriture est validée
    (commit). Chaque appel est inscrit au journal, refus compris."""
    import time
    from app.extensions import db
    from app.services import api_journal
    started = time.monotonic()
    try:
        tool = find(name, key)
        if tool.access == "write" and api_journal.creations_today(key.id) >= key.creations_per_day:
            raise ToolRefused("daily_cap", f"Plafond de {key.creations_per_day} créations par jour atteint pour la clé "
                              f"« {key.name} » : réessayez demain (la lecture reste possible).")
    except ToolRefused as exc:
        found = next((t for t in registry() if t.name == name), None)
        _log(name if found else "?", key, channel, started, tool=found, result={"error": exc.message}, error=True,
             status=429 if exc.code == "daily_cap" else 404 if exc.code == "unknown_tool" else 403)
        raise
    if args is None:
        args = {}
    if not isinstance(args, dict) or not _conforms(tool.schema, args):
        result = {"error": "Arguments non conformes au schéma de l'outil.", "schema": tool.schema}
        _log(name, key, channel, started, tool=tool, result=result, error=True)
        return result, True
    try:
        result = tool.handler(args)
        if tool.access == "write" and not (isinstance(result, dict) and result.get("error")):
            db.session.commit()
        else:
            db.session.rollback()   # lecture, ou écriture refusée : rien n'est gardé
    except Exception:  # noqa: BLE001 — détail au journal du serveur, message générique à l'agent
        from flask import current_app
        db.session.rollback()
        current_app.logger.exception("Outil d'agent %s : erreur", name)
        result = {"error": "Erreur interne de l'outil : réessayez plus tard ou signalez-la à l'administrateur."}
    error = isinstance(result, dict) and bool(result.get("error"))
    _log(name, key, channel, started, tool=tool, args=args, result=result, error=error)
    return result, error


def to_text(result: dict) -> str:
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + " … [résultat tronqué : restreignez la recherche]"
    return text
