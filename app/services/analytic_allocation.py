"""Ventilation analytique des lignes d'écriture (lot AG8.b, claudedocs/design_analytique_agricole.md §§ 4 et 5, AGD25).

- **Lignes concernées** : classes 6 et 7 de l'exercice, hors écritures d'ouverture, de clôture, d'affectation et de
  stock (les variations de stock viennent de l'inventaire, AG8.d), hors 603 / 713 et hors exceptionnel et impôt
  (67, 77, 69). Tous modes de tenue : la comptabilité simplifiée génère aussi des lignes.
- **Affectation** d'une ligne, sans toucher l'écriture : ventilation saisie (une ou plusieurs cibles, total ≤ 100 %),
  sinon règle de compte (préfixe le plus long). Une cible est une **activité** ou une **clé de répartition**.
- **Clés** : surface ou effectif des activités membres sur la campagne de la ligne (déduite des dates de chaque
  activité), pourcentages saisis ramenés à 100, ou marge brute (calculée par l'état des marges, AG8.e).
- **Couverture** : part des charges et des produits affectés.
"""
from __future__ import annotations

import unicodedata
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import or_

from app.extensions import db
from app.models import (Account, Activity, ActivityProduction, AnalyticAllocation, AnalyticKey, AnalyticKeyMember,
                        AnalyticRule, Campaign, FiscalYear, JournalEntry, JournalLine)
from app.models.analytic import ALLOCATION_ORIGINS, KEY_BASES
from app.models.journal_entry import SOURCE_ALLOCATION, SOURCE_CLOSING, SOURCE_OPENING, SOURCE_STOCK
from app.services.analytic import AnalyticError, campaign_year

EXCLUDED_SOURCES = (SOURCE_OPENING, SOURCE_CLOSING, SOURCE_ALLOCATION, SOURCE_STOCK)
EXCLUDED_PREFIXES = ("603", "713", "67", "77", "69")
FULL = 10000
BASIS_UNITS = {"surface": "hectare", "headcount": "head"}


# ------------------------------------------------------------------ cibles

def _target(activity_id, key_id) -> tuple[Activity | None, AnalyticKey | None]:
    activity = db.session.get(Activity, activity_id) if isinstance(activity_id, int) else None
    key = db.session.get(AnalyticKey, key_id) if isinstance(key_id, int) else None
    if (activity is None) == (key is None):
        raise AnalyticError("Choisissez une activité ou une clé de répartition.", "targets")
    return activity, key


def target_payload(activity: Activity | None, key: AnalyticKey | None) -> dict:
    if activity is not None:
        return {"kind": "activity", "id": activity.id, "label": f"{activity.workshop.name} › {activity.name}"}
    return {"kind": "key", "id": key.id, "label": f"Clé « {key.name} »"}


def targets_options() -> list[dict]:
    """Activités (par atelier) et clés, pour les listes de choix."""
    out = []
    activities = sorted(Activity.query.filter(Activity.archived.is_(False)),
                        key=lambda a: (a.workshop.position, a.workshop.name, a.name))
    for activity in activities:
        out.append({"value": f"activity:{activity.id}", "label": activity.name, "group": activity.workshop.name})
    for key in AnalyticKey.query.filter(AnalyticKey.archived.is_(False)).order_by(AnalyticKey.name):
        out.append({"value": f"key:{key.id}", "label": key.name, "group": "Clés de répartition"})
    return out


# ------------------------------------------------------------------ clés

def key_payload(key: AnalyticKey) -> dict:
    warnings = []
    unit = BASIS_UNITS.get(key.basis)
    if not key.members:
        warnings.append("Clé sans activité.")
    if unit and any(m.activity.unit != unit for m in key.members):
        warnings.append("Des activités membres n'ont pas l'unité de la clé (hectares ou têtes).")
    if key.basis == "percentage" and key.members and not sum(m.share_bp or 0 for m in key.members):
        warnings.append("Pourcentages à saisir.")
    return {"id": key.id, "name": key.name, "basis": key.basis, "basis_label": KEY_BASES.get(key.basis, key.basis),
            "note": key.note, "archived": key.archived, "warnings": warnings,
            "members": [{"activity_id": m.activity_id, "activity": m.activity.name, "workshop": m.activity.workshop.name,
                         "share_bp": m.share_bp} for m in key.members]}


def save_key(key: AnalyticKey | None, data: dict) -> AnalyticKey:
    creating = key is None
    key = key or AnalyticKey()
    if creating or "name" in data:
        name = str(data.get("name") or "").strip()[:120]
        if not name:
            raise AnalyticError("Nom obligatoire.", "name")
        if AnalyticKey.query.filter(AnalyticKey.name == name, AnalyticKey.id != (key.id or 0)).first():
            raise AnalyticError("Une clé porte déjà ce nom.", "name", 409)
        key.name = name
    if creating or "basis" in data:
        if data.get("basis") not in KEY_BASES:
            raise AnalyticError("Base de répartition inconnue.", "basis")
        key.basis = data["basis"]
    if "note" in data:
        key.note = str(data.get("note") or "").strip()[:300] or None
    if "archived" in data:
        key.archived = bool(data["archived"])
    if "members" in data:
        rows = data.get("members") or []
        if not isinstance(rows, list):
            raise AnalyticError("Liste d'activités attendue.", "members")
        seen, members = set(), []
        for i, row in enumerate(rows):
            activity = db.session.get(Activity, row.get("activity_id")) if isinstance(row, dict) and isinstance(row.get("activity_id"), int) else None
            if activity is None:
                raise AnalyticError("Activité introuvable.", f"members[{i}].activity_id")
            if activity.id in seen:
                raise AnalyticError("Activité en double.", f"members[{i}].activity_id")
            seen.add(activity.id)
            share = row.get("share_bp")
            if key.basis == "percentage":
                if isinstance(share, bool) or not isinstance(share, int) or not 0 <= share <= FULL:
                    raise AnalyticError("Part en points de base (0 à 10 000) attendue.", f"members[{i}].share_bp")
            else:
                share = None
            members.append(AnalyticKeyMember(activity_id=activity.id, share_bp=share))
        key.members = members
    if creating:
        db.session.add(key)
    db.session.flush()
    return key


def _measure(activity: Activity, year: int) -> Decimal | None:
    row = (ActivityProduction.query.join(Campaign)
           .filter(ActivityProduction.activity_id == activity.id, Campaign.year == year).first())
    return Decimal(row.measure) if row is not None and row.measure is not None else None


def expand(activity: Activity | None, key: AnalyticKey | None, day, campaign: int | None = None) -> dict:
    """Répartition d'une cible à une date : [{activity_id, activity, campaign_year, share (0–1)}], avertissements.
    Base « marge brute » : différée à l'état des marges (AG8.e)."""
    if activity is not None:
        return {"parts": [{"activity_id": activity.id, "activity": activity.name,
                           "campaign_year": campaign or campaign_year(activity, day), "share": Decimal(1)}], "warnings": []}
    if key.basis == "gross_margin":
        return {"parts": [], "deferred": True, "warnings": []}
    weights, warnings = [], []
    for member in key.members:
        year = campaign or campaign_year(member.activity, day)
        if key.basis == "percentage":
            weight = Decimal(member.share_bp or 0)
        else:
            weight = _measure(member.activity, year)
            if weight is None:
                warnings.append(f"{member.activity.name} : mesure de la campagne {year} à saisir.")
                weight = Decimal(0)
        weights.append((member.activity, year, weight))
    total = sum(w for *_x, w in weights)
    if not total:
        warnings.append(f"Clé « {key.name} » : rien à répartir (mesures ou parts nulles).")
        return {"parts": [], "warnings": warnings}
    return {"parts": [{"activity_id": a.id, "activity": a.name, "campaign_year": y, "share": w / total}
                      for a, y, w in weights if w], "warnings": warnings}


# ------------------------------------------------------------------ règles

def rule_payload(rule: AnalyticRule) -> dict:
    return {"id": rule.id, "account_prefix": rule.account_prefix, "target": target_payload(rule.activity, rule.key)}


def save_rule(data: dict) -> AnalyticRule:
    prefix = str(data.get("account_prefix") or "").strip()
    if not prefix.isdigit() or not prefix.startswith(("6", "7")):
        raise AnalyticError("Compte ou préfixe de classe 6 ou 7 attendu.", "account_prefix")
    if prefix.startswith(EXCLUDED_PREFIXES):
        raise AnalyticError("Compte hors analytique (variations de stock, exceptionnel, impôt).", "account_prefix")
    activity, key = _target(data.get("activity_id"), data.get("key_id"))
    rule = AnalyticRule.query.filter_by(account_prefix=prefix).first() or AnalyticRule(account_prefix=prefix)
    rule.activity_id, rule.key_id = (activity.id if activity else None), (key.id if key else None)
    db.session.add(rule)
    db.session.flush()
    return rule


def delete_rule(rule_id: int) -> None:
    rule = db.session.get(AnalyticRule, rule_id)
    if rule is None:
        raise AnalyticError("Règle introuvable.", status=404)
    db.session.delete(rule)


def _rules() -> list[AnalyticRule]:
    return sorted(AnalyticRule.query.all(), key=lambda r: -len(r.account_prefix))


def rule_for(code: str, rules: list[AnalyticRule]) -> AnalyticRule | None:
    return next((r for r in rules if code.startswith(r.account_prefix)), None)


def _normalize(text: str) -> str:
    raw = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return " ".join(raw.replace("'", " ").replace("-", " ").split())


def suggestions(fy: FiscalYear) -> list[dict]:
    """Comptes de l'exercice dont le libellé contient le nom d'une activité, sans règle : règle proposée."""
    rules = _rules()
    used = {code: label for code, label in (db.session.query(Account.code, Account.label).join(JournalLine)
                                            .join(JournalEntry).filter(JournalEntry.fiscal_year_id == fy.id,
                                                                       or_(Account.code.like("6%"), Account.code.like("7%")))
                                            .distinct())}
    out = []
    activities = Activity.query.filter(Activity.archived.is_(False)).all()
    for code, label in sorted(used.items()):
        if code.startswith(EXCLUDED_PREFIXES) or rule_for(code, rules) is not None:
            continue
        text = f" {_normalize(label)} "
        hits = [a for a in activities if len(_normalize(a.name)) >= 3 and f" {_normalize(a.name)} " in text]
        if len(hits) == 1:
            out.append({"account_prefix": code, "account_label": label, "target": target_payload(hits[0], None)})
    return out


# ------------------------------------------------------------------ lignes

def eligible_query(fy: FiscalYear):
    query = (db.session.query(JournalLine, JournalEntry, Account)
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .join(Account, Account.id == JournalLine.account_id)
             .filter(JournalEntry.fiscal_year_id == fy.id,
                     JournalEntry.source.notin_(EXCLUDED_SOURCES),
                     or_(Account.code.like("6%"), Account.code.like("7%"))))
    for prefix in EXCLUDED_PREFIXES:
        query = query.filter(~Account.code.like(f"{prefix}%"))
    return query


def amount(line: JournalLine, code: str) -> int:
    """Montant de la ligne en valeur de charge (classe 6) ou de produit (classe 7) : positif dans le sens normal."""
    return (line.debit_cents - line.credit_cents) if code.startswith("6") else (line.credit_cents - line.debit_cents)


def _manual(line_ids) -> dict[int, list[AnalyticAllocation]]:
    out: dict[int, list[AnalyticAllocation]] = defaultdict(list)
    if line_ids:
        for row in AnalyticAllocation.query.filter(AnalyticAllocation.journal_line_id.in_(list(line_ids))):
            out[row.journal_line_id].append(row)
    return out


def resolve_all(fy: FiscalYear) -> list[dict]:
    """Toutes les lignes concernées avec leur affectation : {line, entry, account, amount, origin, targets, share_bp}."""
    purge_orphans()
    rows = eligible_query(fy).order_by(JournalEntry.entry_date, JournalLine.id).all()
    manual = _manual([l.id for l, _e, _a in rows])
    rules = _rules()
    out = []
    for line, entry, account in rows:
        allocs = manual.get(line.id)
        if allocs:
            targets = [{**target_payload(a.activity, a.key), "share_bp": a.share_bp, "campaign_year": a.campaign_year}
                       for a in allocs]
            origin = allocs[0].origin
        else:
            rule = rule_for(account.code, rules)
            targets = ([{**target_payload(rule.activity, rule.key), "share_bp": FULL, "campaign_year": None}]
                       if rule is not None else [])
            origin = "account" if rule is not None else None
        out.append({"line": line, "entry": entry, "account": account, "amount_cents": amount(line, account.code),
                    "origin": origin, "targets": targets, "share_bp": sum(t["share_bp"] for t in targets)})
    return out


def coverage(items: list[dict]) -> dict:
    out = {}
    for side, prefix in (("charges", "6"), ("products", "7")):
        rows = [i for i in items if i["account"].code.startswith(prefix)]
        total = sum(abs(i["amount_cents"]) for i in rows)
        allocated = sum(round(abs(i["amount_cents"]) * i["share_bp"] / FULL) for i in rows)
        out[side] = {"total_cents": total, "allocated_cents": allocated,
                     "ratio_bp": round(allocated * FULL / total) if total else None}
    return out


def _line_payload(item: dict) -> dict:
    line, entry = item["line"], item["entry"]
    return {"id": line.id, "date": entry.entry_date.isoformat(), "reference": entry.reference,
            "label": line.label or entry.description, "account": item["account"].code, "amount_cents": item["amount_cents"],
            "origin": item["origin"], "origin_label": ALLOCATION_ORIGINS.get(item["origin"]) if item["origin"] else None,
            "targets": item["targets"], "share_bp": item["share_bp"]}


def unallocated(fy: FiscalYear, account: str | None = None, include_allocated: bool = False) -> dict:
    items = resolve_all(fy)
    groups: dict[str, dict] = {}
    for item in items:
        if item["share_bp"] >= FULL and not include_allocated:
            continue
        acc = item["account"]
        group = groups.setdefault(acc.code, {"account": acc.code, "label": acc.label, "count": 0, "amount_cents": 0,
                                            "partial": 0})
        group["count"] += 1
        group["amount_cents"] += round(item["amount_cents"] * (FULL - min(item["share_bp"], FULL)) / FULL) \
            if not include_allocated else item["amount_cents"]
        group["partial"] += 1 if 0 < item["share_bp"] < FULL else 0
    lines = [_line_payload(i) for i in items if account and i["account"].code == account
             and (include_allocated or i["share_bp"] < FULL)]
    return {"fiscal_year": {"id": fy.id, "label": fy.label}, "coverage": coverage(items),
            "groups": sorted(groups.values(), key=lambda g: g["account"]), "lines": lines,
            "suggestions": suggestions(fy)}


def allocate(fy: FiscalYear, line_ids, targets, campaign=None) -> int:
    """Ventilation saisie de lignes : remplace leurs ventilations ; `targets` [{activity_id | key_id, share_bp}]."""
    if not isinstance(line_ids, list) or not line_ids or not all(isinstance(i, int) for i in line_ids):
        raise AnalyticError("Lignes à ventiler attendues.", "line_ids")
    if not isinstance(targets, list) or not targets:
        raise AnalyticError("Au moins une activité ou une clé.", "targets")
    if campaign is not None and (isinstance(campaign, bool) or not isinstance(campaign, int) or not 2000 <= campaign <= 2100):
        raise AnalyticError("Campagne attendue (année).", "campaign_year")
    resolved, total = [], 0
    for i, row in enumerate(targets):
        if not isinstance(row, dict):
            raise AnalyticError("Cible invalide.", f"targets[{i}]")
        activity, key = _target(row.get("activity_id"), row.get("key_id"))
        share = row.get("share_bp", FULL if len(targets) == 1 else None)
        if isinstance(share, bool) or not isinstance(share, int) or not 0 < share <= FULL:
            raise AnalyticError("Part en points de base (1 à 10 000) attendue.", f"targets[{i}].share_bp")
        total += share
        resolved.append((activity, key, share))
    if total > FULL:
        raise AnalyticError("Le total des parts dépasse 100 %.", "targets")
    eligible = {l.id for l, _e, _a in eligible_query(fy).filter(JournalLine.id.in_(line_ids))}
    if len(eligible) != len(set(line_ids)):
        raise AnalyticError("Lignes hors analytique ou d'un autre exercice.", "line_ids")
    AnalyticAllocation.query.filter(AnalyticAllocation.journal_line_id.in_(line_ids)).delete(synchronize_session=False)
    for line_id in line_ids:
        for activity, key, share in resolved:
            db.session.add(AnalyticAllocation(journal_line_id=line_id, activity_id=activity.id if activity else None,
                                              key_id=key.id if key else None, campaign_year=campaign, share_bp=share,
                                              origin="manual"))
    db.session.flush()
    return len(line_ids)


def clear(fy: FiscalYear, line_ids) -> int:
    if not isinstance(line_ids, list) or not all(isinstance(i, int) for i in line_ids):
        raise AnalyticError("Lignes attendues.", "line_ids")
    ids = [l.id for l, _e, _a in eligible_query(fy).filter(JournalLine.id.in_(line_ids))]
    count = AnalyticAllocation.query.filter(AnalyticAllocation.journal_line_id.in_(ids)).delete(synchronize_session=False)
    return count


# ------------------------------------------------------------------ affectation depuis les sources (lot AG8.c)

def parse_target(value, field: str = "analytic_target") -> str | None:
    """« activity:ID » ou « key:ID » existant (valeur vide : aucune affectation)."""
    text = str(value or "").strip()
    if not text:
        return None
    kind, _sep, raw = text.partition(":")
    if kind not in ("activity", "key") or not raw.isdigit():
        raise AnalyticError("Affectation analytique invalide.", field)
    model = Activity if kind == "activity" else AnalyticKey
    if db.session.get(model, int(raw)) is None:
        raise AnalyticError("Activité ou clé introuvable.", field)
    return f"{kind}:{int(raw)}"


def _objects(target: str | None) -> tuple[Activity | None, AnalyticKey | None]:
    if not target:
        return None, None
    kind, _sep, raw = target.partition(":")
    if not raw.isdigit():
        return None, None
    if kind == "activity":
        return db.session.get(Activity, int(raw)), None
    return None, db.session.get(AnalyticKey, int(raw))


def eligible_code(code: str) -> bool:
    return code.startswith(("6", "7")) and not code.startswith(EXCLUDED_PREFIXES)


def attach(line: JournalLine, target: str | None, origin: str = "manual") -> AnalyticAllocation | None:
    """Ventilation à 100 % d'une ligne nouvellement passée (compte de charge ou de produit seulement)."""
    activity, key = _objects(target)
    if activity is None and key is None:
        return None
    account = line.account or db.session.get(Account, line.account_id)
    if account is None or not eligible_code(account.code):
        return None
    row = AnalyticAllocation(journal_line_id=line.id, activity_id=activity.id if activity else None,
                             key_id=key.id if key else None, share_bp=FULL,
                             origin=origin if origin in ALLOCATION_ORIGINS else "manual")
    db.session.add(row)
    return row


def line_target(line: JournalLine) -> str | None:
    """Affectation unique à 100 % d'une ligne (pour la réafficher dans un éditeur), sinon None."""
    rows = list(getattr(line, "analytic_allocations", []) or [])
    if len(rows) != 1 or rows[0].share_bp != FULL:
        return None
    row = rows[0]
    return f"activity:{row.activity_id}" if row.activity_id else f"key:{row.key_id}"


def target_label(target: str | None) -> str | None:
    activity, key = _objects(target)
    if activity is None and key is None:
        return None
    return target_payload(activity, key)["label"]


def purge_orphans() -> None:
    """Ventilations dont la ligne n'existe plus (suppressions en masse sans cascade SQLite)."""
    existing = db.session.query(JournalLine.id)
    AnalyticAllocation.query.filter(AnalyticAllocation.journal_line_id.notin_(existing)).delete(synchronize_session=False)
