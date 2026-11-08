"""Clés d'API de l'instance (lot AK1, claudedocs/design_api_mcp_aiffel.md § 9.1).

- Administrateur de l'instance : toutes les clés de la structure, création, modification, révocation.
- Tout membre : ses propres clés (`/me/api-keys`), révocables par lui.
Une clé ne gère jamais les clés (`api_keys` est fermé aux clés, app/services/api_domains.py).
"""
from flask import g, jsonify
from flask_login import current_user

from app.access import current_role, instance_admin_required
from app.extensions import db
from app.models import ApiKey
from app.models.instance_membership import ROLE_ADMIN
from app.services import api_domains, api_keys
from app.services.api_keys import ApiKeyError

from . import ApiError, bp, json_body, notice


def _error(exc: ApiKeyError) -> ApiError:
    return ApiError("validation_error" if exc.status == 422 else "conflict", exc.message, status=exc.status,
                    fields={exc.field: exc.message} if exc.field else None)


def _meta():
    inst = g.current_instance
    return {"domains": api_domains.options(inst.chart), "members": api_keys.member_options(inst),
            "mcp_url": api_keys.mcp_url(), "defaults": {
                "rate_per_minute": api_keys.DEFAULT_RATE, "creations_per_day": api_keys.DEFAULT_DAILY,
                "days": api_keys.DEFAULT_DAYS, "max_days": api_keys.MAX_DAYS}}


def _key(key_id, own_only=False) -> ApiKey:
    key = db.session.get(ApiKey, key_id)
    if key is None or key.instance_id != g.current_instance.id:
        raise ApiError("not_found", "Clé introuvable.", status=404)
    if own_only and key.user_id != current_user.id and current_role() != ROLE_ADMIN:
        raise ApiError("not_found", "Clé introuvable.", status=404)
    return key


@bp.route("/api-keys")
@instance_admin_required
def api_keys_list():
    items = [api_keys.payload(k, current_user.id) for k in api_keys.for_instance(g.current_instance)]
    return jsonify(items=items, meta=_meta())


@bp.route("/api-keys", methods=["POST"])
@instance_admin_required
def api_keys_create():
    """`{name, user_id, read_domains, write_domains, expires_on?, rate_per_minute?, creations_per_day?}`.
    La clé complète (`token`) n'est rendue qu'ici, une seule fois."""
    try:
        key, token = api_keys.create(g.current_instance, json_body(), current_user)
    except ApiKeyError as exc:
        raise _error(exc) from None
    return jsonify(item=api_keys.payload(key, current_user.id), token=token, mcp_url=api_keys.mcp_url(),
                   notices=[notice(f"Clé « {key.name} » créée : copiez-la maintenant, elle ne sera plus affichée.")]), 201


@bp.route("/api-keys/<int:key_id>", methods=["PATCH"])
@instance_admin_required
def api_keys_update(key_id):
    try:
        key = api_keys.update(_key(key_id), json_body())
    except ApiKeyError as exc:
        raise _error(exc) from None
    return jsonify(item=api_keys.payload(key, current_user.id), notices=[notice(f"Clé « {key.name} » modifiée.")])


@bp.route("/api-keys/<int:key_id>/revoke", methods=["POST"])
def api_keys_revoke(key_id):
    """Administrateur de l'instance, ou l'utilisateur rattaché à la clé."""
    key = api_keys.revoke(_key(key_id, own_only=True), current_user)
    return jsonify(item=api_keys.payload(key, current_user.id),
                   notices=[notice(f"Clé « {key.name} » révoquée : elle ne fonctionne plus.")])


@bp.route("/me/api-keys")
def api_keys_mine():
    items = [api_keys.payload(k, current_user.id) for k in api_keys.for_user(current_user, g.current_instance)]
    return jsonify(items=items, meta={"domains": api_domains.options(g.current_instance.chart),
                                      "mcp_url": api_keys.mcp_url()})
