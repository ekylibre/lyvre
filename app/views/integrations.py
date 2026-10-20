"""Écran des intégrations : index (statut de chaque service) et page de détail
(interrupteur, configuration, test de fonctionnement, dernière synchronisation)."""
from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.decorators import admin_required
from app.extensions import db
from app.models import ExternalConnection
from app.services import external_config, integrations

bp = Blueprint("integrations", __name__, url_prefix="/configuration/integrations")

# Ancienne adresse de l'écran (« Connexions externes ») : favoris et liens existants.
legacy_bp = Blueprint(
    "external_connections", __name__, url_prefix="/configuration/external-connections"
)

# Champ → (libellé, type d'entrée, aide). Le caractère secret vient de external_config.SECRET_KEYS.
# Une entrée (service, champ) prime sur l'entrée par champ (même nom de clé, sens différent).
FIELD_META = {
    ("qonto", "login"):         ("Identifiant (login)", "text",
                                 "Qonto › Intégrations et partenariats › Clé API"),
    ("qonto", "secret_key"):    ("Clé secrète", "password", "Clé API générée dans Qonto"),
    ("qonto", "staging_token"): ("Jeton bac à sable (optionnel)", "password",
                                 "Renseigné = bac à sable Qonto ; vide = production"),
    "secret_key":       ("Clé secrète", "password", "Format sk_xxx, stest_xxx ou sprod_xxx"),
    "mode":             ("Mode", "text", "live ou test"),
    "url":              ("URL", "text", "https://erp.example.org"),
    "db":               ("Base de données", "text", "Nom de la base Odoo"),
    "username":         ("Login", "text", "Souvent un email"),
    "api_key":          ("Clé API", "password", "Clé API Odoo"),
    "client_id":        ("Client ID", "text", ""),
    "client_secret":    ("Client Secret", "password", ""),
    "org_slug":         ("Slug organisation", "text", "helloasso.com/associations/<slug>"),
    "api_base":         ("Base API (optionnel)", "text", "https://api.helloasso.com"),
    "host":             ("Serveur SMTP", "text", "smtp.gmail.com"),
    "port":             ("Port", "text", "587"),
    "use_tls":          ("TLS (true/false)", "text", "true"),
    "password":         ("Mot de passe", "password", "Mot de passe ou mot de passe d'application"),
    "sender":           ("Expéditeur", "text", "Association <contact@exemple.org>"),
    "property_id":      ("ID de propriété GA4", "text", "Ex : 472641442"),
    "credentials_json": ("Clé JSON du compte de service", "textarea",
                         "Coller le contenu du fichier .json"),
    "page_id":          ("ID de la Page", "text", "ID numérique de la Page Facebook"),
    "page_token":       ("Page Access Token", "password", "Token longue durée"),
    "app_id":           ("App ID Meta", "text", ""),
    "app_secret":       ("App Secret Meta", "password", ""),
}

# Écran lié à la dernière synchronisation suivie.
SYNC_LINK_LABELS = {
    "bank_accounts.index": "Comptes bancaires",
    "payouts.index": "Versements Stancer",
    "impact.index": "Visibilité & Impact",
}


def _service_or_404(service):
    if service not in external_config.SERVICE_KEYS:
        abort(404)
    return service


def _db_value(service, key):
    """Valeur enregistrée en base (jamais le repli .env)."""
    row = db.session.query(ExternalConnection).filter_by(service=service, key=key).first()
    return row.value if row is not None and row.value else None


def _fields(service):
    required = set(external_config.SERVICE_REQUIRED_KEYS[service])
    fields = []
    for key in external_config.SERVICE_KEYS[service]:
        label, input_type, help_text = FIELD_META.get(
            (service, key), FIELD_META.get(key, (key, "text", ""))
        )
        secret = (service, key) in external_config.SECRET_KEYS
        source = external_config.source(service, key)
        fields.append({
            "key": key,
            "label": label,
            "input": input_type,
            "help": help_text,
            "required": key in required,
            "secret": secret,
            "source": source,
            # Un secret n'est jamais renvoyé au navigateur.
            "value": "" if secret else (_db_value(service, key) or ""),
            "env_value": None if secret or source != "env" else external_config.get(service, key),
        })
    return fields


@bp.route("/")
@login_required
@admin_required
def index():
    return render_template("integrations/index.html", views=integrations.overview())


@bp.route("/<service>")
@login_required
@admin_required
def detail(service):
    _service_or_404(service)
    return render_template(
        "integrations/detail.html",
        view=integrations.detail(service),
        fields=_fields(service),
        sync_link_labels=SYNC_LINK_LABELS,
    )


@bp.route("/<service>", methods=["POST"])
@login_required
@admin_required
def save(service):
    _service_or_404(service)
    values = {}
    for key in external_config.SERVICE_KEYS[service]:
        submitted = (request.form.get(key) or "").strip()
        if (service, key) in external_config.SECRET_KEYS:
            if request.form.get(f"clear_{key}"):
                values[key] = ""
            else:
                # Champ secret laissé vide : on garde la valeur enregistrée.
                values[key] = submitted or _db_value(service, key) or ""
        else:
            values[key] = submitted
    external_config.set_many(service, values)

    label = external_config.SERVICE_LABELS[service]
    if not external_config.is_enabled(service):
        flash(f"Configuration {label} enregistrée (intégration désactivée, non testée).", "success")
    else:
        result = integrations.run_check(service)
        if result.ok:
            flash(f"Configuration {label} enregistrée. {result.message}", "success")
        elif not external_config.is_configured(service):
            flash(f"Configuration {label} enregistrée. {result.message}", "warning")
        else:
            flash(f"Configuration {label} enregistrée, mais le test a échoué : {result.message}",
                  "danger")
    return redirect(url_for("integrations.detail", service=service))


@bp.route("/<service>/enabled", methods=["POST"])
@login_required
@admin_required
def toggle(service):
    _service_or_404(service)
    enabled = request.form.get("enabled") == "1"
    external_config.set_enabled(service, enabled)
    label = external_config.SERVICE_LABELS[service]
    flash(f"Intégration {label} {'activée' if enabled else 'désactivée'}.", "success")
    return redirect(url_for("integrations.detail", service=service))


@bp.route("/<service>/check", methods=["POST"])
@login_required
@admin_required
def check(service):
    _service_or_404(service)
    result = integrations.run_check(service)
    flash(result.message, "success" if result.ok else "danger")
    return redirect(url_for("integrations.detail", service=service))


@legacy_bp.route("/")
def index_redirect():
    return redirect(url_for("integrations.index"), code=301)
