"""Instances (admin, méta-base seule) : liste, création, import d'un fichier, modification,
sauvegardes `.zip` (création, suppression), restauration. Le téléchargement d'une sauvegarde
reste une route Flask (`instances.download_backup`). L'URL d'une base n'est jamais renvoyée
avec son mot de passe."""
import json
import shutil

from flask import jsonify, request, url_for
from flask_login import current_user
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.decorators import admin_required
from app.extensions import db
from app.models import Instance
from app.services import instance_access, instance_backup
from app.services.attachments import uploads_dir_for
from app.services.instance_access import AccessError
from app.services.instance_backup import BackupError
from app.services.instance_provisioning import (
    CHARTS, DEFAULT_CHART, ProvisioningError, build_sqlite_url, database_file_for_url, discard_sqlite_database,
    provision_sqlite_database, validate_slug,
)
from app.tenant import clear_engine_cache, get_tenant_engine

from . import ApiError, bp, get_or_404, invalid, json_body, notice
from .access import access_error, add_member, members_response, remove_member, update_member


def _iso(value):
    return value.isoformat() if value else None


def masked_url(url: str) -> str:
    """URL de base sans mot de passe (`postgresql://user:***@hôte/base`)."""
    try:
        return make_url(url).render_as_string(hide_password=True)
    except ArgumentError:
        return url.split("://", 1)[0] + "://…" if "://" in url else "…"


def _instance(inst: Instance) -> dict:
    return {"id": inst.id, "slug": inst.slug, "label": inst.label, "database": masked_url(inst.database_url),
            "chart": inst.chart, "chart_label": CHARTS.get(inst.chart, inst.chart), "is_active": inst.is_active,
            "bookkeeping": inst.bookkeeping,
            "created_at": _iso(inst.created_at), "sqlite": instance_backup.is_sqlite_instance(inst)}


def _backups(inst: Instance) -> list[dict]:
    if not instance_backup.is_sqlite_instance(inst):
        return []
    return [{"filename": b.filename, "size_bytes": b.size_bytes, "created_at": _iso(b.created_at),
             "is_pre_restore": b.is_pre_restore, "database_only": b.filename.endswith(".db"),
             "download_url": url_for("instances.download_backup", instance_id=inst.id, filename=b.filename)}
            for b in instance_backup.list_backups(inst)]


def _detail(inst: Instance) -> dict:
    return {"item": _instance(inst), "backups": _backups(inst)}


def _grants(raw):
    """Lignes `members` validées sans écrire (création refusée en entier si l'une est fausse)."""
    try:
        return instance_access.parse_grants(raw)
    except AccessError as exc:
        raise access_error(exc) from None


def _form_members():
    """Champ multipart `members` : JSON de la même forme que pour la création."""
    raw = (request.form.get("members") or "").strip()
    if not raw:
        return []
    try:
        return json.loads(raw)
    except ValueError:
        raise invalid("Utilisateurs illisibles.", "members") from None


def _save_with_grants(inst, grants, cleanup):
    """Instance et accès en une transaction ; en cas d'échec, `cleanup()` retire les fichiers créés."""
    try:
        db.session.add(inst)
        db.session.flush()
        counts = instance_access.apply_grants(inst, grants, current_user)
        db.session.commit()
    except Exception:
        db.session.rollback()
        cleanup()
        raise
    return counts


def _created_notices(message, counts, grants):
    summary = instance_access.grants_summary(counts)
    return [notice(f"{message}{' ; ' + summary if summary else ''}."),
            *(notice(w, level="warning") for w in instance_access.grants_warnings(grants))]


@bp.route("/instances")
@admin_required
def instances_list():
    return jsonify(items=[_instance(i) for i in db.session.query(Instance).order_by(Instance.label)],
                   meta={"charts": [{"value": k, "label": v} for k, v in CHARTS.items()], "default_chart": DEFAULT_CHART})


@bp.route("/instances", methods=["POST"])
@admin_required
def instances_create():
    """`{slug, label, provisioning_mode: auto|manual, chart, database_url, members}` ; `members` :
    `[{user_id, role} | {email, full_name?, password, role}]`, validés avant le provisioning."""
    data = json_body()
    try:
        slug = validate_slug(str(data.get("slug") or ""))
    except ProvisioningError as exc:
        raise invalid(str(exc), "slug") from None
    label = str(data.get("label") or "").strip()[:200]
    if not label:
        raise invalid("Le libellé est obligatoire.", "label")
    if db.session.query(Instance).filter(Instance.slug == slug).first():
        raise invalid(f"L'instance « {slug} » existe déjà.", "slug")
    chart = data.get("chart") if data.get("chart") in CHARTS else DEFAULT_CHART
    bookkeeping = data.get("bookkeeping") or "double"
    if bookkeeping not in ("double", "simple"):
        raise invalid("Mode de tenue inconnu.", "bookkeeping")
    if bookkeeping == "simple" and chart != "asso":
        raise invalid("La comptabilité simplifiée est réservée au plan des associations.", "bookkeeping")
    grants = _grants(data.get("members"))
    auto = data.get("provisioning_mode", "auto") == "auto"
    if auto:
        database_url = build_sqlite_url(slug)
        try:
            provision_sqlite_database(database_url, chart=chart)
        except ProvisioningError as exc:
            raise ApiError("provisioning_failed", f"Échec du provisioning : {exc}", status=422) from None
    else:
        database_url = str(data.get("database_url") or "").strip()
        if not database_url:
            raise invalid("URL de base de données obligatoire en mode manuel.", "database_url")
    inst = Instance(slug=slug, label=label, database_url=database_url, chart=chart, bookkeeping=bookkeeping,
                    has_associates=chart == "sci",
                    is_active=True)
    counts = _save_with_grants(inst, grants, lambda: discard_sqlite_database(database_url) if auto else None)
    return jsonify(item=_instance(inst), notices=_created_notices(f"Instance « {label} » créée", counts, grants)), 201


@bp.route("/instances/<int:instance_id>")
@admin_required
def instances_detail(instance_id):
    return jsonify(_detail(get_or_404(Instance, instance_id, "Instance introuvable.")))


@bp.route("/instances/<int:instance_id>", methods=["PATCH"])
@admin_required
def instances_update(instance_id):
    inst = get_or_404(Instance, instance_id, "Instance introuvable.")
    data = json_body()
    label = str(data.get("label", inst.label) or "").strip()[:200]
    if not label:
        raise invalid("Le libellé est obligatoire.", "label")
    inst.label = label
    if "is_active" in data:
        inst.is_active = bool(data["is_active"])
    if "bookkeeping" in data and data["bookkeeping"] != inst.bookkeeping:
        _change_bookkeeping(inst, data["bookkeeping"])
    db.session.commit()
    clear_engine_cache(inst.id)
    return jsonify(item=_instance(inst), notices=[notice(f"Instance « {label} » mise à jour.")])


def _change_bookkeeping(inst, mode):
    """Passage simple → partie double toujours possible, sans reprise (les opérations simples sont
    déjà des écritures en partie double). L'inverse est refusé dès qu'une écriture ne se lit pas en
    recettes / dépenses : une ligne hors classes 5 (trésorerie), 6 et 7."""
    if mode not in ("double", "simple"):
        raise invalid("Mode de tenue inconnu.", "bookkeeping")
    if mode == "simple":
        if inst.chart != "asso":
            raise invalid("La comptabilité simplifiée est réservée au plan des associations.", "bookkeeping")
        with get_tenant_engine(inst).connect() as conn:
            count = conn.execute(text(
                "SELECT COUNT(DISTINCT l.entry_id) FROM journal_lines l JOIN accounts a ON a.id = l.account_id "
                "WHERE substr(a.code, 1, 1) NOT IN ('5', '6', '7')")).scalar()
        if count:
            raise ApiError("conflict", f"Retour en comptabilité simplifiée impossible : {count} écriture(s) de partie "
                           "double (tiers, immobilisations, capitaux…) ne se lisent pas en recettes et dépenses.", 409)
    inst.bookkeeping = mode


def _sqlite(inst):
    if not instance_backup.is_sqlite_instance(inst):
        raise ApiError("conflict", "Sauvegarde et restauration disponibles uniquement pour les instances SQLite.",
                       status=409)


@bp.route("/instances/<int:instance_id>/backups", methods=["POST"])
@admin_required
def instances_backup(instance_id):
    inst = get_or_404(Instance, instance_id, "Instance introuvable.")
    _sqlite(inst)
    try:
        path = instance_backup.create_backup(inst)
    except BackupError as exc:
        raise ApiError("backup_failed", str(exc), status=422) from None
    return jsonify(**_detail(inst), notices=[notice(f"Sauvegarde créée : {path.name}")]), 201


@bp.route("/instances/<int:instance_id>/backups/<filename>", methods=["DELETE"])
@admin_required
def instances_delete_backup(instance_id, filename):
    inst = get_or_404(Instance, instance_id, "Instance introuvable.")
    try:
        instance_backup.delete_backup(inst, filename)
    except BackupError as exc:
        raise ApiError("not_found", str(exc), status=404) from None
    return jsonify(**_detail(inst), notices=[notice(f"Sauvegarde supprimée : {filename}")])


def _upload():
    uploaded = request.files.get("backup_file")
    if uploaded is None or not uploaded.filename:
        raise invalid("Sélectionnez un fichier.", "backup_file")
    return uploaded


def _restore(inst, uploaded):
    try:
        pre_backup, _ = instance_backup.restore_from_upload(inst, uploaded)
    except BackupError as exc:
        raise invalid(str(exc), "backup_file") from None
    return pre_backup


@bp.route("/instances/<int:instance_id>/restore", methods=["POST"])
@admin_required
def instances_restore(instance_id):
    """Multipart `backup_file` + `confirm` = slug de l'instance (confirmation forte)."""
    inst = get_or_404(Instance, instance_id, "Instance introuvable.")
    _sqlite(inst)
    if (request.form.get("confirm") or "").strip() != inst.slug:
        raise invalid(f"Saisissez « {inst.slug} » pour confirmer la restauration.", "confirm")
    pre_backup = _restore(inst, _upload())
    return jsonify(**_detail(inst), notices=[notice(
        f"Restauration appliquée. Sauvegarde de sécurité créée : {pre_backup.name}")])


@bp.route("/instances/import", methods=["POST"])
@admin_required
def instances_import():
    """Multipart `backup_file`, `slug` (sinon déduit du nom), `label`, `confirm` (= slug si restauration),
    `members` (JSON, création seulement). Slug connu : restauration de l'instance, accès inchangés ;
    sinon création d'une instance sur ce fichier, avec ses utilisateurs."""
    uploaded = _upload()
    slug = (request.form.get("slug") or "").strip().lower() or (
        instance_backup.extract_slug_from_filename(uploaded.filename) or "")
    if not slug:
        raise invalid("Impossible de déduire le slug depuis le nom du fichier : saisissez-en un.", "slug")
    members = _form_members()
    existing = db.session.query(Instance).filter(Instance.slug == slug).first()
    if existing is not None:
        if members:
            raise invalid("Une restauration ne modifie pas les accès : gérez-les depuis la fiche de l'instance.",
                          "members")
        _sqlite(existing)
        if (request.form.get("confirm") or "").strip() != existing.slug:
            raise ApiError("confirmation_required", f"L'instance « {existing.label} » existe : le fichier la "
                           f"remplacera. Saisissez « {slug} » pour confirmer la restauration.", status=409,
                           fields={"confirm": f"Saisissez « {slug} »."})
        pre_backup = _restore(existing, uploaded)
        return jsonify(item=_instance(existing), notices=[notice(
            f"Instance « {existing.label} » restaurée depuis le fichier. Sauvegarde de sécurité : {pre_backup.name}")])

    try:
        slug = validate_slug(slug)
    except ProvisioningError as exc:
        raise invalid(str(exc), "slug") from None
    label = (request.form.get("label") or "").strip()[:200] or slug.replace("-", " ").title()
    grants = _grants(members)
    database_url = build_sqlite_url(slug)
    target = database_file_for_url(database_url)
    if target is None:
        raise invalid("Impossible de calculer le chemin cible.")
    if target.exists() and target.stat().st_size > 0:
        raise ApiError("conflict", f"Le fichier {target.name} existe déjà sans instance enregistrée : déplacez-le ou "
                       "supprimez-le manuellement avant l'import.", status=409)
    try:
        instance_backup.stage_upload_to_path(uploaded, target, slug)
    except BackupError as exc:
        raise invalid(str(exc), "backup_file") from None
    inst = Instance(slug=slug, label=label, database_url=database_url, is_active=True)

    def cleanup():
        discard_sqlite_database(database_url)
        shutil.rmtree(uploads_dir_for(slug), ignore_errors=True)

    counts = _save_with_grants(inst, grants, cleanup)
    return jsonify(item=_instance(inst), notices=_created_notices(
        f"Instance « {label} » créée depuis le fichier (slug : {slug})", counts, grants)), 201


# ------------------------------------------------------------------ accès (fiche instance)


@bp.route("/instances/<int:instance_id>/members")
@admin_required
def instances_members(instance_id):
    """Membres d'une instance, active ou non, depuis sa fiche (mêmes règles que la page Accès)."""
    inst = get_or_404(Instance, instance_id, "Instance introuvable.")
    return members_response(inst, meta={"roles": instance_access.role_options()})


@bp.route("/instances/<int:instance_id>/members", methods=["POST"])
@admin_required
def instances_add_member(instance_id):
    return add_member(get_or_404(Instance, instance_id, "Instance introuvable."))


@bp.route("/instances/<int:instance_id>/members/<int:user_id>", methods=["PATCH"])
@admin_required
def instances_update_member(instance_id, user_id):
    return update_member(get_or_404(Instance, instance_id, "Instance introuvable."), user_id)


@bp.route("/instances/<int:instance_id>/members/<int:user_id>", methods=["DELETE"])
@admin_required
def instances_remove_member(instance_id, user_id):
    return remove_member(get_or_404(Instance, instance_id, "Instance introuvable."), user_id)
