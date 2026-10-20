from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.decorators import admin_required
from app.services import external_config

bp = Blueprint(
    "external_connections", __name__, url_prefix="/configuration/external-connections"
)


def _build_view_data():
    services = []
    for slug, label in external_config.SERVICE_LABELS.items():
        keys = external_config.SERVICE_KEYS[slug]
        required = set(external_config.SERVICE_REQUIRED_KEYS[slug])
        fields = []
        for key in keys:
            fields.append({
                "key": key,
                "value": external_config.get(slug, key) or "",
                "source": external_config.source(slug, key),
                "required": key in required,
            })
        services.append({
            "slug": slug,
            "label": label,
            "configured": external_config.is_configured(slug),
            "fields": fields,
        })
    return services


@bp.route("/")
@login_required
@admin_required
def index():
    return render_template(
        "external_connections/index.html",
        services=_build_view_data(),
    )


@bp.route("/<service>", methods=["POST"])
@login_required
@admin_required
def save(service):
    if service not in external_config.SERVICE_KEYS:
        abort(404)
    values = {key: request.form.get(key, "") for key in external_config.SERVICE_KEYS[service]}
    external_config.set_many(service, values)
    flash(f"Configuration {external_config.SERVICE_LABELS[service]} enregistrée.", "success")
    return redirect(url_for("external_connections.index"))


@bp.route("/smtp/test", methods=["POST"])
@login_required
@admin_required
def test_smtp():
    """Teste la connexion au serveur SMTP configuré pour l'instance."""
    from app.services import integrations

    result = integrations.run_check("smtp")
    flash(result.message, "success" if result.ok else "danger")
    return redirect(url_for("external_connections.index"))
