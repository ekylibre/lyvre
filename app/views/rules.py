from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.services.rules_engine import load_rules, apply_rules, DEFAULT_RULES_PATH

bp = Blueprint("rules", __name__, url_prefix="/rules")


@bp.route("/")
@login_required
def index():
    try:
        rules = load_rules()
        error = None
    except FileNotFoundError:
        rules = []
        error = f"Fichier de règles introuvable : {DEFAULT_RULES_PATH}"
    except Exception as e:
        rules = []
        error = f"Erreur de lecture du fichier de règles : {e}"

    return render_template("rules/index.html", rules=rules, rules_path=str(DEFAULT_RULES_PATH), error=error)


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
