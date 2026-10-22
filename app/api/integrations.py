"""Intégrations (admin) : état de chaque service, fiche (configuration, activation, test de
connexion, dernière synchronisation). Un secret n'est jamais renvoyé : champ vide = valeur
enregistrée conservée, `clear` l'efface."""
from flask import jsonify, url_for

from app.access import instance_admin_required
from app.extensions import db
from app.models import ExternalConnection
from app.services import external_config, integrations

from . import ApiError, bp, invalid, json_body, notice

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



def _service(service):
    if service not in external_config.SERVICE_KEYS:
        raise ApiError("not_found", "Intégration inconnue.", status=404)
    return service


def _db_value(service, key):
    """Valeur enregistrée en base (jamais le repli .env)."""
    row = db.session.query(ExternalConnection).filter_by(service=service, key=key).first()
    return row.value if row is not None and row.value else None


def _fields(service):
    required = set(external_config.SERVICE_REQUIRED_KEYS[service])
    fields = []
    for key in external_config.SERVICE_KEYS[service]:
        label, input_type, help_text = FIELD_META.get((service, key), FIELD_META.get(key, (key, "text", "")))
        secret = (service, key) in external_config.SECRET_KEYS
        source = external_config.source(service, key)
        fields.append({
            "key": key, "label": label, "input": input_type, "help": help_text, "required": key in required,
            "secret": secret, "source": source,
            # Un secret n'est jamais renvoyé au navigateur, ni sa valeur de repli .env.
            "value": "" if secret else (_db_value(service, key) or ""),
            "env_value": None if secret or source != "env" else external_config.get(service, key),
        })
    return fields


def _iso(value):
    return value.isoformat() if value else None


def _view(v) -> dict:
    check = v.last_check
    return {"slug": v.slug, "label": v.label, "description": v.description, "status": v.status,
            "status_label": v.status_label, "enabled": v.enabled, "configured": v.configured,
            "check_outdated": v.check_outdated,
            "last_check": ({"ok": check.ok, "message": check.message, "checked_at": _iso(check.checked_at),
                            "duration_ms": check.duration_ms} if check else None)}


def _detail(service) -> dict:
    v = integrations.detail(service)
    s = v.last_sync
    return {"item": {**_view(v), "sync_tracked": v.sync_tracked, "last_sync": ({
        "status": s.status, "started_at": _iso(s.started_at), "finished_at": _iso(s.finished_at),
        "message": s.message, "imported": s.imported, "errors": list(s.errors),
        "url": url_for(s.endpoint), "link_label": SYNC_LINK_LABELS.get(s.endpoint, "Voir"),
    } if s else None)}, "fields": _fields(service)}


@bp.route("/integrations")
@instance_admin_required
def integrations_list():
    return jsonify(items=[_view(v) for v in integrations.overview()])


@bp.route("/integrations/<service>")
@instance_admin_required
def integrations_detail(service):
    return jsonify(_detail(_service(service)))


@bp.route("/integrations/<service>", methods=["PUT"])
@instance_admin_required
def integrations_save(service):
    """`{values: {clé: valeur}, clear: [clés secrètes à effacer]}` puis test si l'intégration est active."""
    _service(service)
    data = json_body()
    submitted = data.get("values") or {}
    clear = set(data.get("clear") or [])
    if not isinstance(submitted, dict):
        raise invalid("Valeurs attendues.")
    values = {}
    for key in external_config.SERVICE_KEYS[service]:
        value = str(submitted.get(key) or "").strip()
        if (service, key) in external_config.SECRET_KEYS:
            # Secret laissé vide : valeur enregistrée conservée.
            values[key] = "" if key in clear else (value or _db_value(service, key) or "")
        else:
            values[key] = value
    external_config.set_many(service, values)

    label = external_config.SERVICE_LABELS[service]
    if not external_config.is_enabled(service):
        notices = [notice(f"Configuration {label} enregistrée (intégration désactivée, non testée).")]
    else:
        result = integrations.run_check(service)
        if result.ok:
            notices = [notice(f"Configuration {label} enregistrée. {result.message}")]
        elif not external_config.is_configured(service):
            notices = [notice(f"Configuration {label} enregistrée. {result.message}", "warning")]
        else:
            notices = [notice(f"Configuration {label} enregistrée, mais le test a échoué : {result.message}",
                              "danger")]
    return jsonify(**_detail(service), notices=notices)


@bp.route("/integrations/<service>/enabled", methods=["POST"])
@instance_admin_required
def integrations_toggle(service):
    _service(service)
    enabled = bool(json_body().get("enabled"))
    external_config.set_enabled(service, enabled)
    label = external_config.SERVICE_LABELS[service]
    return jsonify(**_detail(service),
                   notices=[notice(f"Intégration {label} {'activée' if enabled else 'désactivée'}.")])


@bp.route("/integrations/<service>/check", methods=["POST"])
@instance_admin_required
def integrations_check(service):
    _service(service)
    if not (external_config.is_enabled(service) and external_config.is_configured(service)):
        raise ApiError("conflict", "Intégration désactivée ou configuration incomplète.", status=409)
    result = integrations.run_check(service)
    return jsonify(**_detail(service), notices=[notice(result.message, "success" if result.ok else "danger")])
