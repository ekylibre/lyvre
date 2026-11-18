"""Session de la SPA : connexion, instance courante, menus, préférences, tâches longues.

Voir claudedocs/design_front_mantine.md §4. Ces routes (sauf ``jobs``) se passent
de la base de l'instance : elles sont déclarées « sans instance » dans app.tenant
(_TENANT_FREE_ENDPOINTS).
"""
import json
from datetime import datetime

from flask import current_app, g, jsonify, session as flask_session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from flask_wtf.csrf import generate_csrf
from sqlalchemy import func

from app.access import accessible_instances, permissions, role_for
from app.extensions import db
from app.menu_config import build_nav
from app.models import Instance, SyncJob, User
from app import demo, version
from app.services import external_config, password_reset, sirene
from app.services.instance_access import MIN_PASSWORD

from . import ApiError, bp, json_body

PREFERENCES_MAX_BYTES = 16 * 1024
COLOR_SCHEMES = ("light", "dark", "auto")

def _current_instance():
    """Instance de la session, si l'utilisateur y a (encore) accès."""
    instance_id = flask_session.get("instance_id")
    inst = db.session.get(Instance, instance_id) if instance_id is not None else None
    return inst if role_for(current_user, inst) is not None else None


def _resolve_nav(menus):
    """Menus de menu_config avec les URL résolues (url_for) pour la SPA, sur trois niveaux (lot NV1), avec l'icône
    Lucide (`icon`) et le pictogramme agric (`pictogram`) de chaque entrée."""
    resolved = []
    for menu in menus:
        if menu.get("divider"):
            resolved.append({"divider": True})
            continue
        entry = {"key": menu["key"], "label": menu["label"]}
        for field in ("icon", "pictogram"):
            if menu.get(field):
                entry[field] = menu[field]
        if "items" in menu:
            entry["items"] = _resolve_nav(menu["items"])
        else:
            entry["url"] = url_for(menu["endpoint"])
            if menu.get("also"):                       # lot NV2 : onglets rattachés à l'entrée
                entry["also_urls"] = [url_for(e) for e in menu["also"]]
        resolved.append(entry)
    return resolved


def preferences_of(user) -> dict:
    try:
        value = json.loads(user.preferences or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _initialize_integrations(inst) -> None:
    """Instance jamais ouverte depuis l'arrivée des interrupteurs en base méta : on l'initialise
    ici (seule lecture de sa base par la session, une fois) pour que les menus soient justes dès
    le premier affichage. Un échec laisse l'initialisation à la première requête de l'instance."""
    from app.tenant import get_tenant_engine

    saved = g.get("current_instance"), g.get("tenant_engine")
    try:
        g.current_instance, g.tenant_engine = inst, get_tenant_engine(inst)
        external_config.ensure_initialized(inst)
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        current_app.logger.warning("Integrations of instance %s not initialized: %r", inst.slug, exc)
    finally:
        g.current_instance, g.tenant_engine = saved


def _enabled_integrations(inst) -> list[str]:
    """Interrupteurs de l'instance (base méta), limités aux intégrations de sa structure."""
    return [s for s in external_config.applicable(inst.chart) if s in inst.enabled_integrations()]


def _integrations(inst, role) -> dict:
    """Intégrations activées (masquages, menus) et, pour l'administrateur de l'instance,
    intégrations recommandées à proposer (tableau de bord)."""
    return {"enabled": _enabled_integrations(inst),
            "proposed": external_config.proposals(inst) if permissions(role).get("instance_admin") else [],
            # Périmètre des intégrations qui en ont un (Qonto : relevés, achats, ventes).
            "scopes": {service: sorted(external_config.scopes(service, inst)) for service in external_config.SCOPES}}


def _features(inst) -> set[str]:
    """Options de l'instance qui conditionnent des menus : module Associés, intégrations activées,
    déclarations de TVA (un exercice les prépare dans Lyvre, lot T3 ; toujours pour une exploitation, dont la page
    indique le régime à renseigner), calculettes (au moins une pour ce type de structure)."""
    from app.services.calculators import charts_covered
    return {*(["associates"] if inst.has_associates else []), *(["vat_returns"] if inst.chart == "agri" or _vat_prepared(inst) else []),
            *(["calculators"] if inst.chart in charts_covered() else []), *_enabled_integrations(inst)}


def _vat_prepared(inst) -> bool:
    """Un exercice de l'instance prépare-t-il la TVA (période déclarative) ?

    La session est une route « sans instance » (app.tenant) : `db.session` y vise la base par
    défaut, pas celle de l'instance. On lit donc la base de l'instance par son propre moteur.
    Base illisible : pas de menu, plutôt qu'une session en erreur."""
    from sqlalchemy import select
    from sqlalchemy.exc import SQLAlchemyError

    from app.models import FiscalYear
    from app.tenant import get_tenant_engine
    try:
        with get_tenant_engine(inst).connect() as conn:
            query = select(FiscalYear.id).where(FiscalYear.vat_period.isnot(None)).limit(1)
            return conn.execute(query).first() is not None
    except SQLAlchemyError:
        current_app.logger.warning("Instance %s : base illisible pour le menu TVA.", inst.slug, exc_info=True)
        return False


def session_payload() -> dict:
    """Utilisateur, instance, menus, préférences et jeton CSRF (vide si non connecté)."""
    if not current_user.is_authenticated:
        return {"user": None, "instance": None, "instances": [], "nav": [], "admin_links": [],
                "role": None, "permissions": permissions(None), "preferences": {},
                "app": version.info(), "demo": demo.session_info(), "csrf_token": generate_csrf()}
    inst = getattr(g, "current_instance", None) or _current_instance()
    is_admin = bool(current_user.is_admin)
    role = role_for(current_user, inst) if inst else None
    if inst is not None and inst.integrations is None:
        _initialize_integrations(inst)
    return {
        "user": {"id": current_user.id, "email": current_user.email,
                 "full_name": current_user.full_name, "is_admin": is_admin,
                 "must_change_password": bool(current_user.must_change_password)},
        "instance": ({"id": inst.id, "slug": inst.slug, "label": inst.label, "chart": inst.chart,
                      "bookkeeping": inst.bookkeeping, "has_associates": bool(inst.has_associates),
                      "integrations": _integrations(inst, role)}
                     if inst else None),
        "instances": [{"id": i.id, "label": i.label} for i in accessible_instances(current_user)],
        "role": role, "permissions": permissions(role),
        "nav": _resolve_nav(build_nav(chart=inst.chart, is_admin=role == "admin", bookkeeping=inst.bookkeeping,
                                      features=_features(inst)))
        if inst else [],
        # Menu de l'utilisateur (en-tête) : administration réservée aux admins.
        "admin_links": ([{"label": "Utilisateurs", "url": url_for("users.index")},
                         {"label": "Instances", "url": url_for("instances.index")},
                         {"label": "Paramètres réglementaires", "url": url_for("regulatory.index")}] if is_admin else []),
        "preferences": _initial_changelog_seen(current_user),
        # Services du serveur (pas d'interrupteur par instance) : Sirene si la clé est configurée.
        "services": {"sirene": sirene.available()},
        "app": version.info(),  # version de Lyvre (data/changelog.yml) et commit déployé
        "demo": demo.session_info(),  # démonstration publique : identifiants affichés, bandeau
        "csrf_token": generate_csrf(),
    }


@bp.route("/changelog")
@login_required
def changelog():
    """Page « Nouveautés » : versions publiées, sans les précisions techniques (lot R2)."""
    return jsonify(items=version.published(), version=version.version())


def _initial_changelog_seen(user) -> dict:
    """Première session : la version courante est réputée vue (pas de pastille sur ce qui précède)."""
    prefs = preferences_of(user)
    if "changelog_seen" not in prefs:
        prefs["changelog_seen"] = version.version()
        user.preferences = json.dumps(prefs, ensure_ascii=False)
        db.session.commit()
    return prefs


@bp.route("/version")
def app_version():
    """Version de Lyvre et commit déployé : publique (page À propos), rien d'autre."""
    return jsonify(version.info())


@bp.route("/session")
@login_required
def session_info():
    return jsonify(session_payload())


@bp.route("/session/login", methods=["POST"])
def login():
    data = json_body()
    email = str(data.get("email") or "").strip().lower()
    password = str(data.get("password") or "")
    user = db.session.query(User).filter(func.lower(User.email) == email).first()
    if user is None or not user.check_password(password):
        raise ApiError("validation_error", "Email ou mot de passe incorrect.", status=422)
    if not user.is_active:
        raise ApiError("validation_error", "Compte désactivé. Contactez un administrateur.", status=422)
    login_user(user)
    user.last_login_at = datetime.utcnow()
    db.session.commit()
    instances = accessible_instances(user)
    if len(instances) == 1 and _current_instance() is None:
        flask_session["instance_id"] = instances[0].id
    return jsonify(session_payload())


@bp.route("/session/logout", methods=["POST"])
def logout():
    flask_session.pop("instance_id", None)
    logout_user()
    return jsonify(session_payload())


@bp.route("/session/password-forgot", methods=["POST"])
def password_forgot():
    """`{email}` : lien de réinitialisation envoyé si un compte actif a cette adresse ; même réponse
    dans tous les cas (pas de découverte des comptes)."""
    password_reset.request_reset(str(json_body().get("email") or ""))
    return jsonify(notices=[{"level": "success", "message": (
        "Si un compte correspond à cette adresse, un e-mail avec un lien de réinitialisation vient de "
        "lui être envoyé (valable une heure). Pensez à regarder les indésirables ; sans e-mail, "
        "contactez un administrateur.")}])


@bp.route("/session/password-reset/check", methods=["POST"])
def password_reset_check():
    """`{token}` : le lien est-il encore valable (page de saisie du nouveau mot de passe) ?"""
    user = password_reset.user_for(str(json_body().get("token") or ""))
    return jsonify(valid=user is not None, email=user.email if user else None)


@bp.route("/session/password-reset", methods=["POST"], endpoint="password_reset")
def password_reset_view():
    """`{token, password}` : nouveau mot de passe ; l'utilisateur se connecte ensuite avec."""
    data = json_body()
    try:
        password_reset.reset(str(data.get("token") or ""), str(data.get("password") or ""))
    except password_reset.ResetError as exc:
        raise ApiError("validation_error", exc.message, status=422, fields={exc.field: exc.message}) from None
    return jsonify(notices=[{"level": "success", "message": "Mot de passe modifié : connectez-vous avec le nouveau."}])


@bp.route("/me/password", methods=["POST"])
@login_required
def change_password():
    """`{current_password, new_password}` : le compte choisit son mot de passe (obligatoire après un
    mot de passe initial ou fixé par un administrateur, cf. `users.must_change_password`)."""
    data = json_body()
    current, new = str(data.get("current_password") or ""), str(data.get("new_password") or "")
    if not current_user.check_password(current):
        raise ApiError("validation_error", "Mot de passe actuel incorrect.", status=422,
                       fields={"current_password": "Mot de passe actuel incorrect."})
    if len(new) < MIN_PASSWORD:
        message = f"{MIN_PASSWORD} caractères au moins."
        raise ApiError("validation_error", message, status=422, fields={"new_password": message})
    if new == current:
        message = "Choisissez un mot de passe différent de l'actuel."
        raise ApiError("validation_error", message, status=422, fields={"new_password": message})
    current_user.set_password(new)
    current_user.must_change_password = False
    db.session.commit()
    return jsonify({**session_payload(), "notices": [{"level": "success", "message": "Mot de passe modifié."}]})


@bp.route("/session/instance", methods=["POST"])
@login_required
def select_instance():
    try:
        instance_id = int(json_body().get("instance_id"))
    except (TypeError, ValueError):
        raise ApiError("validation_error", "Sélection invalide.", status=422,
                       fields={"instance_id": "Choisissez une instance."}) from None
    inst = db.session.get(Instance, instance_id)
    if role_for(current_user, inst) is None:
        raise ApiError("validation_error", "Instance introuvable, désactivée ou non autorisée.", status=422,
                       fields={"instance_id": "Instance introuvable, désactivée ou non autorisée."})
    flask_session["instance_id"] = inst.id
    g.current_instance = inst
    return jsonify(session_payload())


def _merge(base: dict, patch: dict) -> dict:
    """Fusion profonde ; une valeur ``None`` supprime la clé."""
    merged = dict(base)
    for key, value in patch.items():
        if value is None:
            merged.pop(key, None)
        elif isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@bp.route("/me/preferences", methods=["PATCH"])
@login_required
def update_preferences():
    patch = json_body()
    scheme = patch.get("color_scheme")
    if scheme is not None and scheme not in COLOR_SCHEMES:
        raise ApiError("validation_error", "Thème inconnu.", status=422,
                       fields={"color_scheme": "Valeurs possibles : light, dark, auto."})
    merged = _merge(preferences_of(current_user), patch)
    encoded = json.dumps(merged, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode()) > PREFERENCES_MAX_BYTES:
        raise ApiError("payload_too_large", "Préférences trop volumineuses.", status=413)
    current_user.preferences = encoded
    db.session.commit()
    return jsonify(preferences=merged)


def job_payload(job: SyncJob) -> dict:
    try:
        result = json.loads(job.result_json) if job.result_json else None
    except ValueError:
        result = None
    return {"id": job.id, "kind": job.kind, "status": job.status, "message": job.message,
            "progress_done": job.progress_done, "progress_total": job.progress_total,
            "result": result,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None}


@bp.route("/jobs/<int:job_id>")
@login_required
def job_status(job_id):
    job = db.session.get(SyncJob, job_id)
    if job is None:
        raise ApiError("not_found", "Tâche introuvable.", status=404)
    return jsonify(job=job_payload(job))
