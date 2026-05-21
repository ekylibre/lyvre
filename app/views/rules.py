from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models import BankTransaction, Rule
from app.models.rule import RULE_ENTITY_TYPES
from app.services.rules_engine import (
    RuleValidationError,
    apply_rules,
    validate_rule_data,
)

bp = Blueprint("rules", __name__, url_prefix="/rules")


# --- helpers --------------------------------------------------------------


def _form_state_from_rule(rule: Rule | None) -> dict:
    if rule is None:
        return {}
    return {
        "name": rule.name,
        "label_contains": rule.label_contains or "",
        "label_regex": rule.label_regex or "",
        "amount_min": "" if rule.amount_min_cents is None else f"{rule.amount_min_cents / 100:.2f}",
        "amount_max": "" if rule.amount_max_cents is None else f"{rule.amount_max_cents / 100:.2f}",
        "raw_type": rule.raw_type or "",
        "entity_name": rule.entity_name or "",
        "entity_type": rule.entity_type or "",
        "category": rule.category or "",
        "account_code": rule.account_code or "",
        "is_active": rule.is_active,
    }


def _next_position() -> int:
    last = db.session.query(db.func.max(Rule.position)).scalar() or 0
    return last + 1


def _swap_positions(rule_a: Rule, rule_b: Rule) -> None:
    a, b = rule_a.position, rule_b.position
    rule_a.position, rule_b.position = b, a
    db.session.commit()


# --- routes ---------------------------------------------------------------


@bp.route("/")
@login_required
def index():
    rules = db.session.query(Rule).order_by(Rule.position.asc()).all()
    return render_template("rules/index.html", rules=rules)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        try:
            data = validate_rule_data(request.form)
        except RuleValidationError as e:
            flash(str(e), "danger")
            return render_template(
                "rules/form.html", rule=None, form=request.form,
                entity_types=RULE_ENTITY_TYPES,
            )
        rule = Rule(position=_next_position(), **data)
        db.session.add(rule)
        db.session.commit()
        flash(f"Règle « {rule.name} » créée.", "success")
        return redirect(url_for("rules.index"))

    return render_template(
        "rules/form.html", rule=None,
        form={"is_active": True},
        entity_types=RULE_ENTITY_TYPES,
    )


@bp.route("/<int:rule_id>/edit", methods=["GET", "POST"])
@login_required
def edit(rule_id):
    rule = db.session.get(Rule, rule_id)
    if rule is None:
        abort(404)
    if request.method == "POST":
        try:
            data = validate_rule_data(request.form)
        except RuleValidationError as e:
            flash(str(e), "danger")
            return render_template(
                "rules/form.html", rule=rule, form=request.form,
                entity_types=RULE_ENTITY_TYPES,
            )
        for k, v in data.items():
            setattr(rule, k, v)
        db.session.commit()
        flash(f"Règle « {rule.name} » mise à jour.", "success")
        return redirect(url_for("rules.index"))

    return render_template(
        "rules/form.html", rule=rule,
        form=_form_state_from_rule(rule),
        entity_types=RULE_ENTITY_TYPES,
    )


@bp.route("/<int:rule_id>/delete", methods=["POST"])
@login_required
def delete(rule_id):
    rule = db.session.get(Rule, rule_id)
    if rule is None:
        abort(404)
    db.session.delete(rule)
    db.session.commit()
    flash(f"Règle « {rule.name} » supprimée.", "success")
    return redirect(url_for("rules.index"))


@bp.route("/<int:rule_id>/toggle-active", methods=["POST"])
@login_required
def toggle_active(rule_id):
    rule = db.session.get(Rule, rule_id)
    if rule is None:
        abort(404)
    rule.is_active = not rule.is_active
    db.session.commit()
    state = "activée" if rule.is_active else "désactivée"
    flash(f"Règle « {rule.name} » {state}.", "success")
    return redirect(url_for("rules.index"))


@bp.route("/<int:rule_id>/move-up", methods=["POST"])
@login_required
def move_up(rule_id):
    rule = db.session.get(Rule, rule_id)
    if rule is None:
        abort(404)
    neighbor = (
        db.session.query(Rule)
        .filter(Rule.position < rule.position)
        .order_by(Rule.position.desc())
        .first()
    )
    if neighbor is not None:
        _swap_positions(rule, neighbor)
    return redirect(url_for("rules.index"))


@bp.route("/<int:rule_id>/move-down", methods=["POST"])
@login_required
def move_down(rule_id):
    rule = db.session.get(Rule, rule_id)
    if rule is None:
        abort(404)
    neighbor = (
        db.session.query(Rule)
        .filter(Rule.position > rule.position)
        .order_by(Rule.position.asc())
        .first()
    )
    if neighbor is not None:
        _swap_positions(rule, neighbor)
    return redirect(url_for("rules.index"))


@bp.route("/apply", methods=["POST"])
@login_required
def apply():
    overwrite = request.form.get("overwrite") == "1"
    try:
        result = apply_rules(overwrite=overwrite)
        flash(
            f"Règles appliquées : {result['matched']} transaction(s) catégorisée(s), "
            f"{result['posted']} écriture(s) comptable(s) générée(s), "
            f"{result['skipped']} ignorée(s) sur {result['total']} au total.",
            "success",
        )
        for err in result.get("errors", [])[:10]:
            flash(f"Écriture non générée — {err}", "warning")
        if len(result.get("errors", [])) > 10:
            flash(
                f"… et {len(result['errors']) - 10} autre(s) erreur(s) non affichée(s).",
                "warning",
            )
    except Exception as e:
        flash(f"Erreur lors de l'application des règles : {e}", "danger")
    return redirect(url_for("rules.index"))
