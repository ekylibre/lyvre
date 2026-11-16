"""Provision pour hausse de la valeur des stocks de vaches laitières et allaitantes (art. 73 A, lot AG6.d,
claudedocs/design_fiscalite_ba.md § 6, AGD23 ; guide Isacompta du 23/06/2026, BOI-BA-BASE-20-30-20-20 du 22/04/2026).

- **Champ** : réel, IR, sans option 72 B bis, exercices clos du 01/01/2024 au 31/12/2028, vaches en stock (lignes
  d'inventaire marquées laitières ou allaitantes) ; pas le premier exercice d'élevage (sans inventaire précédent).
- **Montant proposé** : hausse de la valeur brute de l'inventaire entre l'ouverture et la clôture, **par catégorie, sans
  compensation** ; dans la limite de 15 000 € × associés exploitants (4 au plus) ; minoré sans contrat pluriannuel
  (EGALIM) à la clôture (10 % en 2025, 20 % en 2026, 25 % ensuite). Le montant ne se fixe pas librement : l'option
  pratique la provision proposée.
- **Comptable** : D 6873 / C 1483 au dernier jour ; reprises D 1483 / C 7873 ; écriture gérée `COW_PROVISION`.
- **Reprises** aux clôtures suivantes : provision ÷ effectif de constitution × vaches sorties (baisse nette d'effectif),
  la plus ancienne d'abord ; pas de reprise si la valeur du stock reste au moins égale à celle de la constitution, ou
  sur dérogation motivée (remplacement avant le dépôt, abattage administratif) ; au **6e exercice**, le solde est
  repris : réintégré, ou **exonéré définitivement** (déduction extra-comptable) si l'effectif ou la valeur a augmenté.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Account, CowProvision, CowProvisionRelease, FiscalYear, JournalEntry, StockLine, TaxOption
from app.models.journal_entry import SOURCE_COW_PROVISION
from app.models.tax_result import COW_CATEGORIES, COW_RELEASE_KINDS
from app.services import reg_params
from app.services.tax_result import TaxResultError


def _p(key: str, fy: FiscalYear, default=None):
    return reg_params.value(key, fy.end_date, default=default)


def _account(code: str, label: str | None = None, parent_code: str | None = None) -> Account:
    account = Account.query.filter_by(code=code, is_header=False).first()
    if account is None:
        if label is None:
            raise TaxResultError(f"Compte {code} absent du plan.", status=409)
        parent = Account.query.filter_by(code=parent_code).first() if parent_code else None
        account = Account(code=code, label=label, account_type=parent.account_type if parent else "EQUITY",
                          parent_id=parent.id if parent else None)
        db.session.add(account)
        db.session.flush()
    return account


def _years() -> list[FiscalYear]:
    return FiscalYear.query.order_by(FiscalYear.start_date).all()


def _previous(fy: FiscalYear) -> FiscalYear | None:
    from app.services.stock_inventory import previous_fiscal_year
    return previous_fiscal_year(fy)


# ------------------------------------------------------------------ inventaire des vaches

def herd(fy: FiscalYear) -> dict:
    """Valeur brute (valeur comptable avant dépréciation) et effectif des vaches en stock, par catégorie, à la clôture."""
    from app.services import stock_inventory
    out = {k: {"value_cents": 0, "heads": 0, "lines": 0} for k in COW_CATEGORIES}
    for line in StockLine.query.filter(StockLine.fiscal_year_id == fy.id, StockLine.cow_category.isnot(None)):
        _unit, value, _w = stock_inventory.evaluate(line, fy)
        heads = line.heads if line.heads is not None else (int(Decimal(line.quantity or 0)) if line.unit == "head" else 0)
        row = out[line.cow_category]
        row["value_cents"] += value or 0
        row["heads"] += heads
        row["lines"] += 1
    return out


def _totals(data: dict) -> tuple[int, int]:
    return sum(r["value_cents"] for r in data.values()), sum(r["heads"] for r in data.values())


# ------------------------------------------------------------------ proposition

def eligibility(fy: FiscalYear) -> tuple[bool, str | None]:
    from app.services import tax_result
    if not tax_result.enabled():
        return False, "Réservé au réel (partie double)."
    if tax_result._is_company_is(fy):  # noqa: SLF001
        return False, "Société à l'impôt sur les sociétés : provision 73 A non applicable."
    first, last = _p("ba.cow.first_close", fy), _p("ba.cow.last_close", fy)
    if first is None or last is None or not date.fromisoformat(first) <= fy.end_date <= date.fromisoformat(last):
        return False, "Exercice hors de la période d'application (exercices clos du 01/01/2024 au 31/12/2028)."
    on = fy.end_date
    if any(o.start_date <= on and (o.renounced_on is None or on < o.renounced_on)
           for o in TaxOption.query.filter_by(code="stock_freeze_72_b_bis")):
        return False, "Option de blocage des stocks (72 B bis) en vigueur : provision 73 A exclue."
    return True, None


def proposal(fy: FiscalYear) -> dict:
    from app.services.dep import operators
    ok, reason = eligibility(fy)
    closing = herd(fy)
    previous = _previous(fy)
    opening = herd(previous) if previous is not None else None
    rows = []
    increase = 0
    for key, label in COW_CATEGORIES.items():
        close = closing[key]["value_cents"]
        open_ = opening[key]["value_cents"] if opening else None
        rise = max(close - (open_ or 0), 0) if opening is not None else 0
        increase += rise
        rows.append({"category": key, "label": label, "opening_cents": open_, "closing_cents": close,
                     "heads": closing[key]["heads"], "increase_cents": rise})
    warnings = []
    if ok and (opening is None or not any(opening[k]["lines"] for k in opening)):
        if any(closing[k]["lines"] for k in closing):
            warnings.append("Pas d'inventaire des vaches à l'ouverture (premier exercice d'élevage ou inventaire précédent "
                            "non marqué) : provision non proposée.")
        increase = 0
    n = operators(fy)
    cap = (_p("ba.cow.cap_cents", fy) or 0) * n
    rate = 0 if fy.egalim_contract else (_p("ba.cow.minoration_bp", fy, 0) or 0)
    amount = round(min(increase, cap) * (10000 - rate) / 10000) if ok else 0
    value, heads = _totals(closing)
    return {"eligible": ok, "reason": reason, "categories": rows, "increase_cents": increase, "cap_cents": cap,
            "operators": n, "egalim_contract": fy.egalim_contract, "minoration_bp": rate, "amount_cents": amount,
            "heads": heads, "value_cents": value, "warnings": warnings}


# ------------------------------------------------------------------ reprises

def remaining(provision: CowProvision, before: FiscalYear | None = None) -> int:
    used = 0
    for r in provision.releases:
        rfy = db.session.get(FiscalYear, r.fiscal_year_id)
        if before is None or rfy.end_date < before.end_date:
            used += r.amount_cents
    return provision.amount_cents - used


def _nth_after(provision: CowProvision, fy: FiscalYear) -> int | None:
    years = [y.id for y in _years()]
    try:
        return years.index(fy.id) - years.index(provision.fiscal_year_id)
    except ValueError:
        return None


def release_plan(fy: FiscalYear) -> list[dict]:
    """Reprises de l'exercice pour les provisions antérieures (calculées)."""
    data = herd(fy)
    value_now, heads_now = _totals(data)
    previous = _previous(fy)
    heads_prev = _totals(herd(previous))[1] if previous is not None else heads_now
    heads_out = max(heads_prev - heads_now, 0)
    years_limit = _p("ba.cow.release_years", fy, 6) or 6
    provisions = sorted((p for p in CowProvision.query.all() if p.fiscal_year.end_date < fy.end_date),
                        key=lambda p: p.fiscal_year.end_date)
    waived = {r.provision_id for r in CowProvisionRelease.query.filter_by(fiscal_year_id=fy.id, kind="waived")}
    plan = []
    for prov in provisions:
        left = remaining(prov, fy)
        nth = _nth_after(prov, fy)
        if left <= 0 or nth is None:
            continue
        if nth == years_limit:
            exempt = heads_now > prov.heads or value_now > prov.value_cents
            plan.append({"provision_id": prov.id, "origin": prov.fiscal_year.label, "kind": "exempt" if exempt else "sixth_year",
                         "heads": None, "amount_cents": left})
            continue
        if heads_out <= 0 or prov.id in waived or value_now >= prov.value_cents or not prov.heads:
            continue
        amount = min(left, round(prov.amount_cents * heads_out / prov.heads))
        used_heads = heads_out if amount < left else round(left * prov.heads / prov.amount_cents)
        plan.append({"provision_id": prov.id, "origin": prov.fiscal_year.label, "kind": "exit", "heads": min(used_heads, heads_out),
                     "amount_cents": amount})
        heads_out -= min(used_heads, heads_out)
    return plan


# ------------------------------------------------------------------ écriture

def entry(fy: FiscalYear) -> JournalEntry | None:
    return JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_COW_PROVISION).first()


def cancel(fy: FiscalYear) -> None:
    from app.services.ledger import delete_entries
    current = entry(fy)
    if fy.status == "closed":
        raise TaxResultError("Exercice clôturé : provision figée.", status=409)
    CowProvisionRelease.query.filter(CowProvisionRelease.fiscal_year_id == fy.id,
                                     CowProvisionRelease.kind != "waived").delete()
    provision = CowProvision.query.filter_by(fiscal_year_id=fy.id).first()
    if provision is not None:
        if any(r.fiscal_year_id != fy.id for r in provision.releases):
            raise TaxResultError("Cette provision a déjà des reprises sur des exercices suivants.", status=409)
        db.session.delete(provision)
    db.session.flush()
    if current is not None:
        if current.is_validated:
            raise TaxResultError("Écriture de la provision validée : annulez d'abord son lot de validation.", status=409)
        (outcome,) = delete_entries([current.id], allow_managed=True)
        if outcome["status"] != "ok":
            raise TaxResultError(outcome.get("message") or "Suppression impossible.", status=409)


def post(fy: FiscalYear, constitute: bool) -> JournalEntry | None:
    """Passe (ou repasse) l'écriture de l'exercice : dotation (option) et reprises calculées (sans commit)."""
    from app.services.assets import _journal
    from app.services.ledger import post_entry
    if fy.status == "closed":
        raise TaxResultError("Exercice clôturé : rouvrez-le pour passer la provision.", status=409)
    cancel(fy)
    prop = proposal(fy)
    lines = []
    provision_account = _account("1483", "Provision pour hausse de la valeur des stocks de vaches (art. 73 A)", "148")
    if constitute:
        if not prop["eligible"]:
            raise TaxResultError(prop["reason"] or "Provision non applicable.", "constitute")
        if prop["amount_cents"] > 0:
            db.session.add(CowProvision(fiscal_year_id=fy.id, amount_cents=prop["amount_cents"], heads=prop["heads"],
                                        value_cents=prop["value_cents"], detail_json=json.dumps(prop["categories"])))
            text = "Dotation provision 73 A (vaches)"
            lines += [{"account_id": _account("6873").id, "label": text, "debit_cents": prop["amount_cents"], "credit_cents": 0},
                      {"account_id": provision_account.id, "label": text, "debit_cents": 0, "credit_cents": prop["amount_cents"]}]
    for r in release_plan(fy):
        db.session.add(CowProvisionRelease(provision_id=r["provision_id"], fiscal_year_id=fy.id, kind=r["kind"],
                                           heads=r["heads"], amount_cents=r["amount_cents"]))
        text = f"Reprise provision 73 A {r['origin']} — {COW_RELEASE_KINDS[r['kind']].lower()}"[:300]
        reversal = _account("7873", "Reprises sur provisions réglementées (stocks)", "787")
        lines += [{"account_id": provision_account.id, "label": text, "debit_cents": r["amount_cents"], "credit_cents": 0},
                  {"account_id": reversal.id, "label": text, "debit_cents": 0, "credit_cents": r["amount_cents"]}]
    db.session.flush()
    if not lines:
        return None
    return post_entry(fy.id, _journal().id, fy.end_date, f"Provision 73 A des vaches {fy.label}", lines,
                      source=SOURCE_COW_PROVISION, commit=False)


def waive(fy: FiscalYear, provision_id, reason: str | None) -> CowProvisionRelease:
    if fy.status == "closed":
        raise TaxResultError("Exercice clôturé.", status=409)
    prov = db.session.get(CowProvision, provision_id) if isinstance(provision_id, int) else None
    if prov is None or prov.fiscal_year.end_date >= fy.end_date:
        raise TaxResultError("Provision antérieure introuvable.", "provision_id", 404)
    text = (str(reason or "").strip()[:300]) or None
    if text is None or len(text) < 5:
        raise TaxResultError("Motif obligatoire (remplacement avant le dépôt, abattage administratif…).", "reason")
    row = CowProvisionRelease(provision_id=prov.id, fiscal_year_id=fy.id, kind="waived", amount_cents=0, reason=text)
    db.session.add(row)
    db.session.flush()
    return row


# ------------------------------------------------------------------ restitution

def register(fy: FiscalYear) -> list[dict]:
    out = []
    for prov in sorted(CowProvision.query.all(), key=lambda p: p.fiscal_year.end_date):
        if prov.fiscal_year.end_date > fy.end_date:
            continue
        out.append({"id": prov.id, "origin": prov.fiscal_year.label, "amount_cents": prov.amount_cents, "heads": prov.heads,
                    "value_cents": prov.value_cents, "remaining_cents": remaining(prov, None),
                    "releases": [{"fiscal_year": db.session.get(FiscalYear, r.fiscal_year_id).label, "kind": r.kind,
                                  "kind_label": COW_RELEASE_KINDS[r.kind], "heads": r.heads, "amount_cents": r.amount_cents,
                                  "reason": r.reason} for r in prov.releases]})
    return out


def view(fy: FiscalYear) -> dict:
    current = entry(fy)
    return {"proposal": proposal(fy), "plan": release_plan(fy), "register": register(fy),
            "constituted": CowProvision.query.filter_by(fiscal_year_id=fy.id).first() is not None,
            "entry": {"id": current.id, "reference": current.reference} if current else None,
            "categories": [{"value": k, "label": v} for k, v in COW_CATEGORIES.items()]}


def tax_lines(fy: FiscalYear) -> list[dict]:
    """Exonération définitive au 6e exercice : la reprise comptée en 7873 est déduite extra-comptablement."""
    return [{"key": f"cow_exempt_{r.id}", "source": "cow_provision", "amount_cents": -r.amount_cents,
             "label": f"Provision 73 A {r.provision.fiscal_year.label} : exonération définitive au 6e exercice"}
            for r in CowProvisionRelease.query.filter_by(fiscal_year_id=fy.id, kind="exempt")]


def checks(fy: FiscalYear) -> list[tuple[str, str, int, str]]:
    from app.services import tax_result
    if not tax_result.enabled():
        return []
    out = []
    if entry(fy) is None:
        plan = release_plan(fy)
        if plan:
            out.append(("cow_release", "Provision 73 A : reprises de l'exercice à passer (sorties de vaches, 6e exercice)",
                        len(plan), "anomaly"))
        prop = proposal(fy)
        if prop["eligible"] and prop["amount_cents"] > 0:
            out.append(("cow_option", "Provision 73 A possible sur la hausse de valeur des vaches (option)", 1, "info"))
    return out
