"""Outils de l'assistant (lot AG9b, claudedocs/design_assistant_agricole.md § 5).

Chaque outil est une fonction fine qui **appelle un service existant** dans la requête Flask (instance et rôle déjà
posés) et rend un dictionnaire JSON, montants formatés en euros. Liste fermée, triée par nom (préfixe en cache
stable) ; les outils de proposition (AG9b.c) ne sont donnés qu'aux rôles admin et treasurer.
AG9b.a : `get_context` (dossier) et `get_agenda` (échéancier).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

MAX_RESULT_CHARS = 20_000
MAX_AGENDA_DAYS = 400


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict
    handler: Callable[[dict], dict]
    propose: bool = False                     # outil de proposition (rôles admin / treasurer) : handler(args, ctx)
    # Mode strict de l'API : au plus 24 paramètres facultatifs sur l'ensemble des outils stricts. Les outils qui en ont
    # beaucoup (recherche, brouillons) restent non stricts ; `run` contrôle leurs arguments.
    strict: bool = True

    def definition(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self.schema, "strict": self.strict}


def euros(cents: int | None) -> str | None:
    if cents is None:
        return None
    sign = "-" if cents < 0 else ""
    value = f"{abs(cents) / 100:,.2f}".replace(",", " ").replace(".", ",")
    return f"{sign}{value} €"


def _schema(properties: dict | None = None, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties or {}, "required": required or [],
            "additionalProperties": False}


def _base_type(prop: dict) -> tuple[str, bool]:
    """(type JSON, null permis) d'une propriété de schéma."""
    kind = prop.get("type")
    if isinstance(kind, list):
        return next((k for k in kind if k != "null"), "null"), "null" in kind
    return kind, False


# ------------------------------------------------------------------ get_context

def get_context(_args: dict) -> dict:
    from app.models import FiscalYear
    from app.services import agri_profile, organization, tax_profile
    from app.tenant import current_instance

    org = organization.get()
    inst = current_instance()
    today = date.today()
    regimes = {kind: tax_profile.current_value(kind, today) for kind in ("income_tax", "ba_regime", "vat_regime")}
    years = FiscalYear.query.order_by(FiscalYear.start_date.desc()).limit(4).all()
    profile = agri_profile.get()
    return {
        "structure": {"name": org.name, "legal_form": org.legal_form_code, "siren": getattr(org, "siren", None),
                      "chart": getattr(inst, "chart", None), "bookkeeping": getattr(inst, "bookkeeping", None)},
        "regimes": regimes,
        "fiscal_years": [{"id": fy.id, "label": fy.label, "start": fy.start_date.isoformat(),
                          "end": fy.end_date.isoformat(), "status": fy.status} for fy in years],
        "agricultural_profile": {k: v for k, v in profile.items() if k != "leases"},
        "leases": len(profile.get("leases") or []),
        "today": today.isoformat(),
    }


# ------------------------------------------------------------------ get_agenda

def get_agenda(args: dict) -> dict:
    from app.services import agenda

    today = date.today()
    try:
        start = date.fromisoformat(args["from"]) if args.get("from") else today - timedelta(days=30)
        end = date.fromisoformat(args["to"]) if args.get("to") else today + timedelta(days=60)
    except ValueError:
        return {"error": "Dates attendues au format AAAA-MM-JJ."}
    if end < start or (end - start).days > MAX_AGENDA_DAYS:
        return {"error": f"Période invalide ou supérieure à {MAX_AGENDA_DAYS} jours."}
    data = agenda.occurrences(start, end, today)
    items = []
    for item in data["items"]:
        if item["quiet"] and item["status"] == "done":
            continue
        items.append({"date": item["date"].isoformat(), "deadline_id": item["deadline_id"], "fiche": item["fiche_id"],
                      "title": item["title"],
                      "label": item["label"], "organism": item["organism"], "period": item["period"],
                      "status": item["status"], "amount": euros(item["amount_cents"]),
                      "amount_estimated": item["amount_proposed"], "to_confirm": item["to_confirm"],
                      "reliability": item["reliability"], "payment": item["payment"],
                      "reminder_only": item["reminder_only"], "link": item["link"]})
    return {"from": start.isoformat(), "to": end.isoformat(), "today": today.isoformat(), "items": items,
            "questions": data.get("questions", [])}


# ------------------------------------------------------------------ lecture (lot AG9b.b)

def _fiscal_year(args: dict):
    """Exercice demandé (libellé), sinon celui qui contient la date du jour, sinon le plus récent."""
    from app.models import FiscalYear
    label = args.get("fiscal_year")
    if label:
        fy = FiscalYear.query.filter_by(label=str(label)).first()
        if fy is None:
            raise LookupError(f"Exercice « {label} » introuvable.")
        return fy
    today = date.today()
    fy = FiscalYear.query.filter(FiscalYear.start_date <= today, FiscalYear.end_date >= today).first()
    return fy or FiscalYear.query.order_by(FiscalYear.end_date.desc()).first()


def _fy_payload(fy) -> dict:
    return {"label": fy.label, "start": fy.start_date.isoformat(), "end": fy.end_date.isoformat(), "status": fy.status}


def _guard(fn):
    def wrapper(args: dict) -> dict:
        try:
            return fn(args)
        except LookupError as exc:
            return {"error": str(exc)}
    return wrapper


@_guard
def get_balances(args: dict) -> dict:
    from app.models import Account
    from app.services import closing
    fy = _fiscal_year(args)
    if fy is None:
        return {"error": "Aucun exercice."}
    prefixes = [p for p in (args.get("prefixes") or "").replace(",", " ").split() if p.isdigit()][:10]
    if not prefixes:
        return {"error": "Préfixes de comptes attendus (ex. « 512 401 »)."}
    balances = closing._balances(fy, tuple(prefixes))  # noqa: SLF001
    labels = {a.code: a.label for a in Account.query.filter(Account.code.in_(list(balances)))}
    rows = [{"account": code, "label": labels.get(code), "balance": euros(value),
             "side": "débiteur" if value > 0 else "créditeur" if value < 0 else "soldé"}
            for code, value in sorted(balances.items())][:200]
    return {"fiscal_year": _fy_payload(fy), "accounts": rows, "total_debit_minus_credit": euros(sum(balances.values()))}


@_guard
def search_entries(args: dict) -> dict:
    from app.models import Account, JournalEntry, JournalLine
    from app.extensions import db
    fy = _fiscal_year(args)
    if fy is None:
        return {"error": "Aucun exercice."}
    query = (db.session.query(JournalLine, JournalEntry, Account).join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .join(Account, Account.id == JournalLine.account_id).filter(JournalEntry.fiscal_year_id == fy.id))
    prefix = (args.get("account_prefix") or "").strip()
    if prefix:
        if not prefix.isdigit():
            return {"error": "Préfixe de compte numérique attendu."}
        query = query.filter(Account.code.like(f"{prefix}%"))
    text = (args.get("text") or "").strip()
    if text:
        like = f"%{text[:80]}%"
        query = query.filter(db.or_(JournalLine.label.ilike(like), JournalEntry.description.ilike(like)))
    try:
        if args.get("date_from"):
            query = query.filter(JournalEntry.entry_date >= date.fromisoformat(args["date_from"]))
        if args.get("date_to"):
            query = query.filter(JournalEntry.entry_date <= date.fromisoformat(args["date_to"]))
    except ValueError:
        return {"error": "Dates attendues au format AAAA-MM-JJ."}
    rows = query.order_by(JournalEntry.entry_date.desc(), JournalLine.id.desc()).limit(21).all()
    lines = [{"date": e.entry_date.isoformat(), "reference": e.reference, "account": a.code, "account_label": a.label,
              "label": l.label or e.description, "debit": euros(l.debit_cents) if l.debit_cents else None,
              "credit": euros(l.credit_cents) if l.credit_cents else None, "validated": e.validation_number is not None}
             for l, e, a in rows[:20]]
    return {"fiscal_year": _fy_payload(fy), "lines": lines, "more": len(rows) > 20}


@_guard
def get_vat(args: dict) -> dict:
    from app.models import VatReturn
    from app.services import tax_profile
    fy = _fiscal_year(args)
    if fy is None:
        return {"error": "Aucun exercice."}
    returns = (VatReturn.query.filter(VatReturn.period_end >= fy.start_date, VatReturn.period_start <= fy.end_date)
               .order_by(VatReturn.period_start).all())
    return {"fiscal_year": _fy_payload(fy), "vat_regime": tax_profile.current_value("vat_regime", fy.end_date),
            "returns": [{"form": r.form, "period": f"{r.period_start.isoformat()} → {r.period_end.isoformat()}",
                         "status": r.status, "due": euros(r.due_cents), "credit": euros(r.credit_cents),
                         "refund_requested": euros(r.refund_cents), "deadline": r.deadline.isoformat() if r.deadline else None,
                         "declared_on": r.declared_on.isoformat() if r.declared_on else None} for r in returns],
            "note": "Acomptes, échéances et montants à venir : outil get_agenda."}


@_guard
def get_tax_result(args: dict) -> dict:
    from app.services import tax_result
    fy = _fiscal_year(args)
    if fy is None or not tax_result.enabled():
        return {"error": "Résultat fiscal indisponible (exercice absent ou comptabilité simplifiée)."}
    data = tax_result.view(fy)
    return {"fiscal_year": _fy_payload(fy), "accounting_result": euros(data["accounting_result_cents"]),
            "lines": [{"label": l["label"], "amount": euros(l["amount_cents"]), "source": l.get("source"),
                       "to_validate": bool(l.get("to_validate"))} for l in data["lines"]],
            "fiscal_result": euros(data["fiscal_result_cents"]), "company_is": data["company_is"],
            "associates": [{"name": a["name"], "share_percent": a["share_bp"] / 100,
                            "fiscal_result": euros(a.get("fiscal_result_cents"))} for a in data["associates"]],
            "warnings": data["warnings"], "frozen": data["frozen"]}


@_guard
def get_msa(args: dict) -> dict:
    from app.services import msa, msa_calls
    fy = _fiscal_year(args)
    if fy is None or not msa.enabled():
        return {"error": "MSA indisponible (exercice absent ou comptabilité simplifiée)."}
    data = msa.view(fy)
    people = []
    for item in data["people"]:
        comp, est = item.get("comparison") or {}, item.get("estimate") or {}
        people.append({"name": item["person"]["name"], "status": item["person"]["status_label"],
                       "option": item["person"]["base_option_label"],
                       "income_before_allowance": euros(item["income_cents"]),
                       "allowance": euros((item["abatement"] or {}).get("amount_cents")),
                       "social_base": euros(item["base_cents"]),
                       "lines": [{"label": l["label"], "amount": euros(l["amount_cents"])} for l in item["lines"]],
                       "next_contribution_year": comp.get("contribution_year"),
                       "annual_base": euros(comp.get("annual_cents")), "triennial_base": euros(comp.get("triennial_cents")),
                       "option_deadline": (comp.get("option") or {}).get("deadline_label"),
                       "estimate_total": euros((est.get("totals") or {}).get("total_cents")) if est.get("available") else None,
                       "estimate_note": None if est.get("available") else est.get("reason")})
    calls = msa_calls.listing(fy.end_date.year)
    return {"fiscal_year": _fy_payload(fy), "revenue_year": data["year"], "reason": data.get("reason"), "people": people,
            "calls": [{"name": p["person"]["name"], "total": euros(p["totals"]["amount_cents"]),
                       "paid": euros(p["totals"]["paid_cents"]), "count": len(p["calls"])} for p in calls["people"]],
            "warnings": data["warnings"] + calls["warnings"]}


@_guard
def get_margins(args: dict) -> dict:
    from app.services import analytic, analytic_margins
    fy = _fiscal_year(args)
    if fy is None or not analytic.enabled():
        return {"error": "Marges indisponibles."}
    campaign = args.get("campaign")
    data = analytic_margins.view(fy, int(campaign) if campaign and str(campaign).isdigit() else None)
    rows = [{"workshop": p["workshop"], "activity": p["activity"], "campaign": p["campaign_year"],
             "measure": f"{p['measure']} {p['unit_label']}" if p["measure"] else None,
             "production": euros(p["production_cents"]), "operational_charges": euros(p["operational_cents"]),
             "gross_margin": euros(p["gross_margin_cents"]),
             "gross_margin_per_unit": euros(p["gross_margin_per_unit_cents"]),
             "result_after_auxiliaries": euros(p.get("result_after_cents", p["result_cents"]))} for p in data["productions"]]
    rec = data.get("reconciliation") or {}
    return {"fiscal_year": _fy_payload(fy), "productions": rows,
            "unallocated_result": euros(data["unallocated"]["result_cents"]),
            "accounting_result": euros(rec.get("accounting_result_cents")), "warnings": data["warnings"][:10]}


@_guard
def get_aids(args: dict) -> dict:
    from app.services import aids
    campaign = args.get("campaign")
    rows = aids.listing(int(campaign) if campaign and str(campaign).isdigit() else None)
    out = []
    for aid in rows[:40]:
        p = aids.payload(aid, with_payments=False)
        out.append({"label": p["label"], "scheme": p["scheme_label"], "campaign": p["campaign"], "status": p["status_label"],
                    "acquired": euros(p["acquired_cents"]), "paid": euros(p["paid_cents"]),
                    "remaining": euros(p["remaining_cents"]), "warnings": p["warnings"]})
    return {"aids": out, "more": len(rows) > 40}


@_guard
def get_closing_checks(args: dict) -> dict:
    from app.services import closing
    fy = _fiscal_year(args)
    if fy is None:
        return {"error": "Aucun exercice."}
    checks = closing.checks(fy)
    return {"fiscal_year": _fy_payload(fy),
            "checks": [{"label": c.label, "count": c.count, "severity": "anomalie (motif exigé)" if c.severity == "anomaly"
                        else "information", "link": c.url} for c in checks]}


def get_parameter(args: dict) -> dict:
    from app.services import reg_params
    key = (args.get("key") or "").strip()
    try:
        on = date.fromisoformat(args["date"]) if args.get("date") else date.today()
    except ValueError:
        return {"error": "Date attendue au format AAAA-MM-JJ."}
    param = reg_params.get(key, on, None) if key else None
    if param is None:
        close = [p["key"] for p in reg_params.listing(key.rsplit(".", 1)[0] if "." in key else key, on)][:20]
        return {"error": f"Paramètre « {key} » inconnu ou sans valeur au {on:%d/%m/%Y}.", "similar_keys": close}
    data = param.payload()
    return {k: data[k] for k in ("key", "value", "valid_from", "valid_to", "source", "source_label", "verified_on",
                                 "reliability", "reliability_label", "note")}


def get_deadline_fiche(args: dict) -> dict:
    from app.services import deadlines
    fiche = deadlines.fiche((args.get("id") or "").strip().upper())
    if fiche is None:
        return {"error": "Fiche inconnue (identifiants du corpus, ex. FIS-03)."}
    return fiche


# ------------------------------------------------------------------ propositions (lot AG9b.c)
#
# Aucune n'écrit en comptabilité : chacune enregistre une `AssistantProposal` que l'interface affiche en carte ;
# l'utilisateur ouvre l'écran prérempli et enregistre lui-même (AG9.8).

NAV_PREFIXES = ("/agenda/", "/vat-returns/", "/rfa/", "/aids/", "/inventory/", "/tax-result/", "/msa/", "/activities/",
                "/analytic/", "/entries/", "/bank-accounts/", "/assets/", "/configuration/organization/",
                "/fiscal-years/", "/reconciliation/")


def _cents_from(text, field: str) -> int:
    from decimal import Decimal, InvalidOperation
    raw = str(text or "0").replace("\u202f", "").replace(" ", "").replace("€", "").replace(",", ".")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise ValueError(f"{field} : montant invalide ({text}).") from None
    if value < 0:
        raise ValueError(f"{field} : montant positif attendu.")
    return int((value * 100).quantize(Decimal(1)))


def _store(ctx: dict, kind: str, payload: dict, summary: str) -> dict:
    from app.extensions import db
    from app.models import AssistantProposal
    row = AssistantProposal(message_id=ctx["message_id"], kind=kind, payload_json=json.dumps(payload, ensure_ascii=False))
    db.session.add(row)
    db.session.commit()
    action = {"id": row.id, "kind": kind, "payload": payload, "summary": summary, "status": "open"}
    ctx.setdefault("actions", []).append(action)
    return {"proposal_id": row.id, "shown_to_user": True,
            "message": "Brouillon affiché à l'utilisateur, NON enregistré : il l'ouvre et l'enregistre lui-même."}


def propose_entry(args: dict, ctx: dict) -> dict:
    from app.models import Account, FiscalYear, Journal
    try:
        day = date.fromisoformat(args.get("date") or "")
    except ValueError:
        return {"error": "Date attendue au format AAAA-MM-JJ."}
    fy = FiscalYear.query.filter(FiscalYear.start_date <= day, FiscalYear.end_date >= day).first()
    if fy is None or fy.closed:
        return {"error": f"Aucun exercice ouvert au {day:%d/%m/%Y}."}
    journal = Journal.query.filter_by(code=(args.get("journal") or "OD").strip().upper()).first()
    if journal is None:
        return {"error": "Journal inconnu (codes : " + ", ".join(j.code for j in Journal.query.order_by(Journal.code)) + ")."}
    lines, debit, credit = [], 0, 0
    for i, raw in enumerate(args.get("lines") or []):
        account = Account.query.filter_by(code=str(raw.get("account") or "").strip()).first()
        if account is None or account.is_header:
            return {"error": f"Ligne {i + 1} : compte « {raw.get('account')} » inconnu ou d'en-tête."}
        try:
            d, c = _cents_from(raw.get("debit"), f"Ligne {i + 1}"), _cents_from(raw.get("credit"), f"Ligne {i + 1}")
        except ValueError as exc:
            return {"error": str(exc)}
        if bool(d) == bool(c):
            return {"error": f"Ligne {i + 1} : un débit ou un crédit, pas les deux."}
        debit, credit = debit + d, credit + c
        lines.append({"account": account.code, "account_label": account.label, "label": (raw.get("label") or "")[:300],
                      "debit_cents": d, "credit_cents": c})
    if len(lines) < 2 or debit != credit:
        return {"error": f"Écriture déséquilibrée ou incomplète (débit {euros(debit)}, crédit {euros(credit)})."}
    payload = {"date": day.isoformat(), "journal": journal.code, "label": (args.get("label") or "")[:300], "lines": lines}
    return _store(ctx, "entry", payload, f"Écriture du {day:%d/%m/%Y} ({journal.code}) de {euros(debit)}")


def propose_msa_call(args: dict, ctx: dict) -> dict:
    from app.models import MsaPerson
    from app.models.msa import MSA_CALL_KINDS
    from app.services.msa import person_name
    people = MsaPerson.query.all()
    wanted = (args.get("person") or "").strip().lower()
    person = next((p for p in people if person_name(p).lower() == wanted or wanted in person_name(p).lower()), None) \
        if wanted else (people[0] if len(people) == 1 else None)
    if person is None:
        return {"error": "Exploitant introuvable.", "people": [person_name(p) for p in people]}
    kind = args.get("kind")
    if kind not in MSA_CALL_KINDS:
        return {"error": "Nature d'appel inconnue.", "kinds": list(MSA_CALL_KINDS)}
    try:
        due = date.fromisoformat(args.get("due_on") or "")
    except ValueError:
        return {"error": "Date attendue au format AAAA-MM-JJ."}
    try:
        amount = _cents_from(args.get("amount"), "Montant")
        csg_d = _cents_from(args["csg_deductible"], "CSG déductible") if args.get("csg_deductible") else None
        csg_n = _cents_from(args["csg_non_deductible"], "CSG non déductible") if args.get("csg_non_deductible") else None
    except ValueError as exc:
        return {"error": str(exc)}
    payload = {"person_id": person.id, "person": person_name(person), "kind": kind, "year": due.year, "due_on": due.isoformat(),
               "amount_cents": amount, "csg_deductible_cents": csg_d, "csg_crds_non_deductible_cents": csg_n}
    return _store(ctx, "msa_call", payload, f"{MSA_CALL_KINDS[kind]} MSA du {due:%d/%m/%Y} : {euros(amount)} ({person_name(person)})")


def propose_deadline(args: dict, ctx: dict) -> dict:
    from app.services import agenda
    status = args.get("action")
    if status not in ("done", "skipped"):
        return {"error": "Action « done » (faite) ou « skipped » (ignorée, avec une note) attendue."}
    note = (args.get("note") or "").strip()[:300] or None
    if status == "skipped" and not note:
        return {"error": "Une échéance ignorée demande une note (motif)."}
    try:
        occurs_on = date.fromisoformat(args.get("occurs_on") or "")
        occ = agenda.find_occurrence((args.get("deadline_id") or "").strip(), occurs_on, args.get("period") or "", date.today())
    except ValueError:
        return {"error": "Date attendue au format AAAA-MM-JJ."}
    except agenda.AgendaError as exc:
        return {"error": exc.message}
    if occ["managed"] and not occ["payment"]:
        return {"error": "Échéance suivie par sa déclaration dans Lyvre : elle ne se marque pas à la main."}
    payload = {"deadline_id": occ["deadline_id"], "occurs_on": occurs_on.isoformat(), "period": occ["period"],
               "status": status, "note": note, "title": f"{occ['title']} — {occ['label']}"}
    verb = "faite" if status == "done" else "ignorée"
    return _store(ctx, "deadline", payload, f"Marquer {verb} : {occ['label']} du {occurs_on:%d/%m/%Y}")


def navigate(args: dict, ctx: dict) -> dict:
    route = (args.get("route") or "").strip()
    if not route.startswith(NAV_PREFIXES) or any(c in route for c in ('"', "<", ">", " ")):
        return {"error": "Écran inconnu (routes de la carte des écrans)."}
    label = (args.get("label") or "Voir l'écran")[:80]
    return _store(ctx, "navigate", {"route": route[:200], "label": label}, label)


# ------------------------------------------------------------------ registre

FY_PROP = {"fiscal_year": {"type": "string", "description": "Libellé de l'exercice (ex. « 2026 ») ; défaut : exercice en cours"}}

# ------------------------------------------------------------------ calculettes (lot AG12.e)

MAX_TABLE_ROWS = 30


def list_calculators(args: dict) -> dict:
    """Calculettes du type de la structure (ou toutes) : code, titre, entrées attendues."""
    from app.services import calculators
    from app.tenant import current_instance
    inst = current_instance()
    chart = inst.chart if inst is not None else None
    query = (args.get("query") or "").strip().lower()
    out = []
    for module in calculators.registry().values():
        spec = module.SPEC
        if chart and chart not in spec.charts:
            continue
        if query and query not in f"{spec.title} {spec.summary} {spec.code}".lower():
            continue
        out.append({"code": spec.code, "number": spec.number, "title": spec.title, "summary": spec.summary,
                    "prefillable": hasattr(module, "prefill"),
                    "inputs": [{"key": i.key, "label": i.label, "kind": i.kind, "unit": i.unit, "required": i.required,
                                "choices": [v for v, _ in i.choices] if i.choices else None, "default": i.default}
                               for i in spec.inputs]})
    out.sort(key=lambda c: c["number"])
    return {"calculators": out, "note": "Montants en euros (ex. « 1234,56 »), dates AAAA-MM-JJ, point « latitude,longitude »."}


def run_calculator(args: dict) -> dict:
    """Calcul d'une calculette, identique à l'écran (règle du service, paramètres datés, méthode) ; rien n'est
    enregistré. `prefill` : valeurs de la structure pour les entrées non fournies."""
    from app.services import calculators
    from app.services.calculators import CalculatorError, Context
    from app.tenant import current_instance
    try:
        module = calculators.get(args.get("code") or "")
    except CalculatorError:
        return {"error": f"Calculette « {args.get('code')} » inconnue : voir list_calculators."}
    values, origins = {}, {}
    if args.get("prefill") and hasattr(module, "prefill"):
        inst = current_instance()
        for key, item in (module.prefill(Context(chart=inst.chart if inst else None)) or {}).items():
            values[key], origins[key] = item["value"], item["origin"]
    for pair in args.get("values") or []:
        if isinstance(pair, dict) and pair.get("key"):
            values[pair["key"]] = pair.get("value")
            origins.pop(pair["key"], None)
    try:
        result = calculators.run(module, values, origins)
    except CalculatorError as exc:
        expected = [i.key for i in module.SPEC.inputs if i.required]
        return {"error": exc.message, "field": exc.field,
                "hint": f"Passez les entrées dans « values » : [{{\"key\": …, \"value\": …}}] ; obligatoires : {', '.join(expected)}."}
    table = result["table"]
    if table and len(table["rows"]) > MAX_TABLE_ROWS:
        table = {**table, "rows": table["rows"][:MAX_TABLE_ROWS], "truncated": True}
    return {"calculator": module.SPEC.title, "values": values, "origins": origins, "headline": result["headline"],
            "details": result["details"], "table": table, "warnings": result["warnings"], "method": module.SPEC.method,
            "params": [{k: p[k] for k in ("key", "value", "valid_from", "source", "source_label", "reliability")}
                       for p in result["params"]],
            "link": f"/outils/{module.SPEC.code}"}


TOOLS: tuple[Tool, ...] = (
    Tool("list_calculators", "Calculettes de Lyvre (fiscal, social, TVA, gestion, cultures, élevage, réglementaire) : code, "
         "titre, entrées attendues. À consulter avant run_calculator ; filtre facultatif sur un mot.",
         _schema({"query": {"type": "string", "description": "Mot recherché, ex. « DEP », « semis », « MSA »"}}),
         list_calculators),
    Tool("run_calculator", "Exécute une calculette (même calcul que l'écran Outils › Calculettes : méthode, paramètres "
         "datés et sources) sans rien enregistrer. Valeurs en paires clé / valeur (clés de list_calculators) ; prefill : "
         "compléter avec les chiffres de la structure quand la calculette le permet.",
         _schema({"code": {"type": "string", "description": "Code de la calculette, ex. dep, micro-ba, calc-dose-semis"},
                  "values": {"type": "array", "items": _schema({"key": {"type": "string"}, "value": {"type": "string"}},
                                                               ["key", "value"])},
                  "prefill": {"type": "boolean", "description": "Préremplir depuis la structure (défaut : non)"}},
                 ["code", "values"]), run_calculator),
    Tool("get_aids", "Dossiers d'aides et subventions (PAC, DJA, investissement…) : montant acquis, versé, restant dû, alertes.",
         _schema({"campaign": {"type": "string", "description": "Campagne (année), facultative"}}), get_aids),
    Tool("get_balances", "Soldes des comptes de l'exercice commençant par les préfixes donnés (ex. « 512 » banque, « 401 » "
         "fournisseurs, « 44 » TVA et État, « 646 » cotisations de l'exploitant).",
         _schema({"prefixes": {"type": "string", "description": "Préfixes séparés par des espaces"}, **FY_PROP},
                 ["prefixes"]), get_balances),
    Tool("get_closing_checks", "Contrôles de clôture de l'exercice (anomalies et informations) avec le lien vers l'écran.",
         _schema(FY_PROP), get_closing_checks),
    Tool("get_deadline_fiche", "Fiche complète d'une échéance du corpus (règles de date, applicabilité, sources).",
         _schema({"id": {"type": "string", "description": "Identifiant, ex. FIS-03"}}, ["id"]), get_deadline_fiche),
    Tool("get_margins", "Marges par activité et par atelier (production, charges opérationnelles, marge brute, par hectare "
         "ou par tête, résultat après auxiliaires).",
         _schema({**FY_PROP, "campaign": {"type": "string", "description": "Campagne (année), facultative"}}), get_margins),
    Tool("get_msa", "Cotisations MSA : assiette sociale par exploitant, option triennale ou annuelle et délais, estimation "
         "indicative des cotisations, appels enregistrés et payés.", _schema(FY_PROP), get_msa),
    Tool("get_parameter", "Paramètre réglementaire daté (seuil, taux, barème) : valeur à une date, source, fiabilité.",
         _schema({"key": {"type": "string", "description": "Clé du corpus, ex. ba.micro.threshold_cents"},
                  "date": {"type": "string", "description": "AAAA-MM-JJ ; défaut : aujourd'hui"}}, ["key"]), get_parameter),
    Tool("get_tax_result", "Résultat fiscal BA de l'exercice : passage du résultat comptable (stocks, abattage, JA, DEP, 73 A, "
         "plus-values…), répartition par associé, alertes.", _schema(FY_PROP), get_tax_result),
    Tool("get_vat", "Déclarations de TVA de l'exercice (CA12A, CA3, acomptes) : statut, montant dû, crédit, remboursement, "
         "échéance, date de dépôt.", _schema(FY_PROP), get_vat),
    Tool("navigate", "Propose un lien vers un écran de Lyvre (carte des écrans du corpus), filtré si besoin.",
         _schema({"route": {"type": "string", "description": "Chemin, ex. /msa/?fiscal_year=3"},
                  "label": {"type": "string", "description": "Texte du bouton"}}, ["route", "label"]), navigate, propose=True),
    Tool("propose_deadline", "Propose de marquer une échéance de l'échéancier faite (done) ou ignorée (skipped, avec note). "
         "L'utilisateur confirme lui-même. Identifiants : deadline_id, date et période renvoyés par get_agenda.",
         _schema({"deadline_id": {"type": "string"}, "occurs_on": {"type": "string"}, "period": {"type": "string"},
                  "action": {"type": "string", "enum": ["done", "skipped"]}, "note": {"type": "string"}},
                 ["deadline_id", "occurs_on", "period", "action"]), propose_deadline, propose=True),
    Tool("propose_entry", "Prépare un BROUILLON d'écriture équilibrée (montants en euros, ex. « 1234,56 ») que "
         "l'utilisateur ouvre dans la saisie et enregistre lui-même. Rien n'est passé en comptabilité.",
         _schema({"date": {"type": "string", "description": "AAAA-MM-JJ"},
                  "journal": {"type": "string", "description": "Code du journal (OD par défaut)"},
                  "label": {"type": "string"},
                  "lines": {"type": "array", "items": _schema({"account": {"type": "string"}, "label": {"type": "string"},
                                                               "debit": {"type": "string"}, "credit": {"type": "string"}},
                                                              ["account"])}},
                 ["date", "lines"]), propose_entry, propose=True, strict=False),
    Tool("propose_msa_call", "Prépare l'enregistrement d'un appel de cotisations MSA reçu (formulaire des appels prérempli, "
         "enregistré par l'utilisateur). Montants en euros.",
         _schema({"person": {"type": "string", "description": "Exploitant (nom) ; facultatif s'il n'y en a qu'un"},
                  "kind": {"type": "string", "enum": ["first", "second", "balance", "monthly", "single", "regularization"]},
                  "due_on": {"type": "string"}, "amount": {"type": "string"}, "csg_deductible": {"type": "string"},
                  "csg_non_deductible": {"type": "string", "description": "CSG non déductible + CRDS"}},
                 ["kind", "due_on", "amount"]), propose_msa_call, propose=True, strict=False),
    Tool("search_entries", "Lignes d'écriture de l'exercice (20 au plus, plus récentes d'abord), filtrées par compte, texte "
         "ou dates.", _schema({**FY_PROP, "account_prefix": {"type": "string"}, "text": {"type": "string"},
                               "date_from": {"type": "string"}, "date_to": {"type": "string"}}), search_entries, strict=False),
    Tool("get_agenda",
         "Échéancier de l'exploitation (TVA, impôts, MSA, PAC, baux…) entre deux dates : date, fiche, organisme, statut "
         "(à venir, à préparer, prête, faite, en retard), montant connu ou estimé, fiabilité. Par défaut, de J-30 à J+60.",
         _schema({"from": {"type": "string", "description": "Début, AAAA-MM-JJ (facultatif)"},
                  "to": {"type": "string", "description": "Fin, AAAA-MM-JJ (facultatif)"}}),
         get_agenda),
    Tool("get_context",
         "Identité et situation du dossier : forme juridique, régimes (impôt, BA, TVA), exercices et leur statut, profil "
         "agricole (productions, caisse MSA, démarches), date du jour.",
         _schema(), get_context),
)


def for_role(can_propose: bool) -> list[Tool]:
    return sorted((t for t in TOOLS if can_propose or not t.propose), key=lambda t: t.name)


def run(name: str, args, can_propose: bool, ctx: dict | None = None) -> tuple[str, bool]:
    """(contenu JSON du résultat, erreur ?). L'outil doit être autorisé pour le rôle. `ctx` : message de la
    réponse (`message_id`) ; les propositions affichées s'ajoutent à `ctx["actions"]`."""
    tool = next((t for t in for_role(can_propose) if t.name == name), None)
    if tool is None:
        return json.dumps({"error": f"Outil inconnu ou non autorisé : {name}."}, ensure_ascii=False), True
    if not isinstance(args, dict):
        return json.dumps({"error": "Arguments invalides (objet JSON attendu)."}, ensure_ascii=False), True
    allowed = set(tool.schema["properties"])
    expected = {"string": str, "array": list, "boolean": bool}

    def conforms(key) -> bool:
        kind, nullable = _base_type(tool.schema["properties"][key])
        value = args[key]
        if value is None:
            return nullable
        return kind not in expected or isinstance(value, expected[kind])

    if set(args) - allowed or not all(conforms(k) for k in args):
        return json.dumps({"error": "Arguments non conformes au schéma de l'outil."}, ensure_ascii=False), True
    if tool.propose and not (ctx and ctx.get("message_id")):
        return json.dumps({"error": "Proposition impossible hors conversation."}, ensure_ascii=False), True
    try:
        result = tool.handler(args, ctx) if tool.propose else tool.handler(args)
    except Exception as exc:  # noqa: BLE001 — l'erreur de l'outil est rendue au modèle, pas à l'utilisateur
        return json.dumps({"error": f"{type(exc).__name__} : {exc}"[:500]}, ensure_ascii=False), True
    text = json.dumps(result, ensure_ascii=False, default=str)
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + ' … [résultat tronqué : restreignez la recherche]'
    return text, bool(isinstance(result, dict) and result.get("error"))
