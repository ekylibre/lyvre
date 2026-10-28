"""Règles de catégorisation des transactions bancaires (ordre, activation, application)."""
from flask import jsonify

from app.extensions import db
from app.models import Rule
from app.models.rule import RULE_ENTITY_TYPES
from app.services import projects
from app.services.rules_engine import RuleValidationError, apply_rules, validate_rule_data

from . import bp, get_or_404, invalid, json_body, notice


def rule_payload(r: Rule) -> dict:
    return {
        "id": r.id, "position": r.position, "name": r.name,
        "label_contains": r.label_contains, "label_regex": r.label_regex,
        "amount_min_cents": r.amount_min_cents, "amount_max_cents": r.amount_max_cents,
        "raw_type": r.raw_type, "entity_name": r.entity_name, "entity_type": r.entity_type,
        "category": r.category, "account_code": r.account_code, "is_active": r.is_active,
        "project_id": r.project_id, "project": r.project.name if r.project else None,
    }


def _form(data: dict) -> dict:
    """Champs JSON (montants en centimes) → formulaire de rules_engine.validate_rule_data."""
    form = {key: "" if data.get(key) is None else str(data.get(key))
            for key in ("name", "label_contains", "label_regex", "raw_type", "entity_name",
                        "entity_type", "category", "account_code", "project_id")}
    for key in ("amount_min", "amount_max"):
        cents = data.get(f"{key}_cents")
        if cents in (None, ""):
            form[key] = ""
        elif isinstance(cents, int) and not isinstance(cents, bool):
            form[key] = f"{cents / 100:.2f}"
        else:
            raise invalid("Montants min/max invalides.", f"{key}_cents")
    form["is_active"] = "1" if data.get("is_active", True) else ""
    return form


def _validated(data):
    try:
        return validate_rule_data(_form(data))
    except RuleValidationError as e:
        raise invalid(str(e)) from None


def _ordered():
    return Rule.query.order_by(Rule.position.asc()).all()


@bp.route("/rules")
def rules_list():
    rules = _ordered()
    return jsonify(items=[rule_payload(r) for r in rules],
                   meta={"entity_types": RULE_ENTITY_TYPES,
                         "projects": projects.options([r.project_id for r in rules if r.project_id])})


@bp.route("/rules", methods=["POST"])
def rules_create():
    data = _validated(json_body())
    last = db.session.query(db.func.max(Rule.position)).scalar() or 0
    rule = Rule(position=last + 1, **data)
    db.session.add(rule)
    db.session.commit()
    return jsonify(item=rule_payload(rule), notices=[notice(f"Règle « {rule.name} » créée.")]), 201


@bp.route("/rules/<int:rule_id>", methods=["PATCH"])
def rules_update(rule_id):
    rule = get_or_404(Rule, rule_id, "Règle introuvable.")
    data = json_body()
    if set(data) == {"is_active"}:
        rule.is_active = bool(data["is_active"])
        db.session.commit()
        state = "activée" if rule.is_active else "désactivée"
        return jsonify(item=rule_payload(rule), notices=[notice(f"Règle « {rule.name} » {state}.")])
    for key, value in _validated(data).items():
        setattr(rule, key, value)
    db.session.commit()
    return jsonify(item=rule_payload(rule), notices=[notice(f"Règle « {rule.name} » mise à jour.")])


@bp.route("/rules/<int:rule_id>", methods=["DELETE"])
def rules_delete(rule_id):
    rule = get_or_404(Rule, rule_id, "Règle introuvable.")
    db.session.delete(rule)
    db.session.commit()
    return jsonify(notices=[notice(f"Règle « {rule.name} » supprimée.")])


@bp.route("/rules/<int:rule_id>/move", methods=["POST"])
def rules_move(rule_id):
    """`{"direction": "up" | "down"}` : échange avec la règle voisine."""
    rule = get_or_404(Rule, rule_id, "Règle introuvable.")
    direction = json_body().get("direction")
    if direction not in ("up", "down"):
        raise invalid("Direction inconnue.", "direction")
    neighbor_query = Rule.query.filter(
        Rule.position < rule.position if direction == "up" else Rule.position > rule.position)
    neighbor = neighbor_query.order_by(
        Rule.position.desc() if direction == "up" else Rule.position.asc()).first()
    if neighbor is not None:
        rule.position, neighbor.position = neighbor.position, rule.position
        db.session.commit()
    return jsonify(items=[rule_payload(r) for r in _ordered()])


@bp.route("/rules/apply", methods=["POST"])
def rules_apply():
    overwrite = bool(json_body().get("overwrite"))
    result = apply_rules(overwrite=overwrite)
    notices = [notice(
        f"Règles appliquées : {result['matched']} transaction(s) catégorisée(s), "
        f"{result['posted']} écriture(s) comptable(s) générée(s), "
        f"{result['skipped']} ignorée(s) sur {result['total']} au total.")]
    errors = result.get("errors", [])
    notices += [notice(f"Écriture non générée — {err}", "warning") for err in errors[:10]]
    if len(errors) > 10:
        notices.append(notice(f"… et {len(errors) - 10} autre(s) erreur(s) non affichée(s).", "warning"))
    return jsonify(result={k: result[k] for k in ("matched", "posted", "skipped", "total")},
                   notices=notices)


# ------------------------------------------------------------------ propositions depuis un mois

def _month(text):
    from app.services.vat_return import VatReturnError, parse_period
    try:
        return parse_period(text)
    except VatReturnError as exc:
        raise invalid(str(exc), "period") from None


def _suggestion_payload(s) -> dict:
    from app.services.rule_suggestions import SOURCE_LABELS
    return {"pattern": s.pattern, "status": s.status, "reason": s.reason, "creatable": s.creatable,
            "entity": s.entity.name if s.entity else None, "account_code": s.account_code,
            "accounts": sorted(s.accounts), "count": len(s.transactions),
            "sources": {SOURCE_LABELS[k]: v for k, v in s.sources.items()},
            "examples": sorted({t.label for t in s.transactions})[:3],
            "rule": {"id": s.rule.id, "name": s.rule.name, "account_code": s.rule.account_code,
                     "entity_name": s.rule.entity_name} if s.rule else None,
            "shadowed_by": {"id": s.shadowed_by.id, "name": s.shadowed_by.name} if s.shadowed_by else None}


@bp.route("/rules/suggestions")
def rules_suggestions():
    """Règles proposées depuis le mois `?period=AAAA-MM` (relevés et factures réglées), `?bank_account_id=`."""
    from flask import request

    from app.services import rule_suggestions
    start, end = _month(request.args.get("period"))
    items = rule_suggestions.suggest(start, end, request.args.get("bank_account_id", type=int))
    return jsonify(items=[_suggestion_payload(s) for s in items])


@bp.route("/rules/suggestions", methods=["POST"])
def rules_suggestions_apply():
    """`{period, patterns: [...], bank_account_id?}` : crée ou recrée les règles des motifs choisis."""
    from app.services import rule_suggestions
    data = json_body()
    patterns = data.get("patterns")
    if not isinstance(patterns, list) or not patterns:
        raise invalid("Choisissez au moins une règle.", "patterns")
    start, end = _month(data.get("period"))
    result = rule_suggestions.apply(start, end, patterns, data.get("bank_account_id"))
    return jsonify(result=result, notices=[notice(
        f"Règles : {result['created']} créée(s), {result['updated']} mise(s) à jour. "
        "« Appliquer les règles » les passe sur les transactions non catégorisées.")])
