"""Rapport d'activité : exercice et mode éco (pro-rata), textes (admin, import du site),
tonnages éco-organismes (admin, import xlsx), photos et logo (admin), versions archivées.
L'aperçu HTML, le PDF, les exports et les fichiers restent servis par Flask
(app/views/activity_report.py) : le PDF est inchangé."""
import os

from flask import current_app, jsonify, request, url_for
from flask_login import current_user
from werkzeug.utils import secure_filename

from app.access import instance_admin_required
from app.extensions import db
from app.models import EcoDeclaration, FiscalYear, ReportArchive, ReportAsset, ReportContent
from app.services import branding, report_pdf, site_content_import
from app.services.activity_report_service import NARRATIVE_BLOCKS, SECTIONS
from app.services.eco_declaration_import import import_eco_xlsx

from . import ApiError, bp, get_or_404, invalid, json_body, notice

PHOTO_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _iso(value):
    return value.isoformat() if value else None


def _fiscal_year(fy_id=None):
    """Exercice demandé, sinon le plus récent ; 409 s'il n'y en a aucun."""
    fy_id = fy_id if fy_id is not None else request.args.get("fy_id", type=int)
    fy = db.session.get(FiscalYear, fy_id) if fy_id else None
    fy = fy or FiscalYear.query.order_by(FiscalYear.start_date.desc()).first()
    if fy is None:
        raise ApiError("no_fiscal_year", "Aucun exercice comptable. Créez-en un dans Compta › Exercices.", status=409)
    return fy


def _prorata():
    raw = request.args.get("prorata")
    if raw is None:
        return bool(current_app.config.get("ECO_PRORATA", False))
    return raw.lower() in ("1", "true", "yes", "on")


@bp.route("/activity-report")
def activity_report_context():
    fy = _fiscal_year()
    prorata = _prorata()
    args = {"fy_id": fy.id, "prorata": 1 if prorata else 0}
    return jsonify(
        fiscal_years=[{"value": str(f.id), "label": f.label}
                      for f in FiscalYear.query.order_by(FiscalYear.start_date.desc())],
        fiscal_year={"id": fy.id, "label": fy.label}, prorata=prorata,
        links={"preview": url_for("activity_report.preview", **args), "pdf": url_for("activity_report.pdf_view", **args),
               **{fmt: url_for("activity_report.export_view", fmt=fmt, **args) for fmt in ("html", "docx", "odt")}},
    )


# ------------------------------------------------------------------ textes


@bp.route("/activity-report/texts")
@instance_admin_required
def activity_report_texts():
    fy = _fiscal_year()
    existing = {c.block_key: c for c in ReportContent.query.filter_by(fiscal_year_id=fy.id)}
    available = site_content_import.available()
    return jsonify(fiscal_year={"id": fy.id, "label": fy.label}, blocks=[
        {"key": key, "label": label, "title": existing[key].title or "" if key in existing else "",
         "body": existing[key].body_html or "" if key in existing else ""} for key, label in NARRATIVE_BLOCKS
    ], site={"available": available, "preview": [
        {"block_key": p["block_key"], "filename": p["filename"], "count": p.get("count")}
        for p in (site_content_import.preview() if available else [])]})


@bp.route("/activity-report/texts", methods=["PUT"])
@instance_admin_required
def activity_report_texts_save():
    data = json_body()
    fy = _fiscal_year(data.get("fy_id"))
    blocks = {b.get("key"): b for b in data.get("blocks") or [] if isinstance(b, dict)}
    existing = {c.block_key: c for c in ReportContent.query.filter_by(fiscal_year_id=fy.id)}
    for key, _label in NARRATIVE_BLOCKS:
        if key not in blocks:
            continue
        title = str(blocks[key].get("title") or "").strip()[:200] or None
        body = str(blocks[key].get("body") or "")
        row = existing.get(key)
        if not body.strip() and title is None:
            if row is not None:
                db.session.delete(row)
            continue
        if row is None:
            row = ReportContent(fiscal_year_id=fy.id, block_key=key)
            db.session.add(row)
        row.title, row.body_html = title, body
        row.updated_by_user_id = getattr(current_user, "id", None)
    db.session.commit()
    return jsonify(notices=[notice("Textes du rapport enregistrés.")])


@bp.route("/activity-report/texts/import-site", methods=["POST"])
@instance_admin_required
def activity_report_import_site():
    data = json_body()
    result = site_content_import.import_site_content(_fiscal_year(data.get("fy_id")), overwrite=bool(data.get("overwrite")))
    if result["errors"]:
        raise ApiError("import_failed", "Import site : " + " ; ".join(result["errors"]), status=422)
    return jsonify(notices=[notice(f"Import site : {len(result['imported'])} bloc(s) pré-rempli(s), "
                                   f"{len(result['skipped'])} ignoré(s).")])


# ------------------------------------------------------------------ tonnages éco-organismes


def _eco_rows():
    return [{"id": r.id, "organism": r.organism, "material": r.material, "quarter": r.quarter_label,
             "entrant_t": float(r.entrant_t or 0), "sortant_t": float(r.sortant_t or 0),
             "financing_cents": r.financing_cents or 0, "source": r.source}
            for r in EcoDeclaration.query.order_by(EcoDeclaration.organism, EcoDeclaration.material,
                                                   EcoDeclaration.period_start)]


@bp.route("/activity-report/eco")
@instance_admin_required
def activity_report_eco():
    return jsonify(items=_eco_rows())


@bp.route("/activity-report/eco", methods=["PUT"])
@instance_admin_required
def activity_report_eco_save():
    """`{rows: [{id, entrant_t, sortant_t, financing_cents, delete?}]}` : lignes modifiées seulement."""
    rows = {r.id: r for r in EcoDeclaration.query.all()}
    errors = {}
    for item in json_body().get("rows") or []:
        row = rows.get(item.get("id")) if isinstance(item, dict) else None
        if row is None:
            continue
        if item.get("delete"):
            db.session.delete(row)
            continue
        try:
            entrant, sortant = float(item["entrant_t"]), float(item["sortant_t"])
            financing = int(item["financing_cents"])
        except (KeyError, TypeError, ValueError):
            errors[str(row.id)] = "Valeurs numériques attendues."
            continue
        if min(entrant, sortant, financing) < 0:
            errors[str(row.id)] = "Valeurs positives attendues."
            continue
        row.entrant_t, row.sortant_t, row.financing_cents, row.source = entrant, sortant, financing, "manual"
    if errors:
        db.session.rollback()
        raise ApiError("validation_error", "Valeurs invalides.", status=422, fields=errors)
    db.session.commit()
    return jsonify(items=_eco_rows(), notices=[notice("Tonnages éco-organismes enregistrés.")])


@bp.route("/activity-report/eco/import", methods=["POST"])
@instance_admin_required
def activity_report_eco_import():
    file = request.files.get("file")
    if file is None or not file.filename:
        raise invalid("Choisissez un fichier .xlsx.", "file")
    if not file.filename.lower().endswith(".xlsx"):
        raise invalid("Fichier .xlsx attendu.", "file")
    try:
        result = import_eco_xlsx(file.stream)
    except Exception as exc:  # classeur illisible ou feuille « Bilan » absente
        db.session.rollback()
        raise invalid(f"Erreur d'import : {exc}", "file") from None
    level = "warning" if result["errors"] else "success"
    return jsonify(items=_eco_rows(), notices=[notice(
        f"Import : {result['imported']} ligne(s) créée(s), {result['updated']} mise(s) à jour, "
        f"{len(result['errors'])} erreur(s).", level)] + [notice(str(e), "warning") for e in result["errors"][:5]])


# ------------------------------------------------------------------ photos et logo


def _slots():
    return [("cover", "Couverture")] + [(f"section_{s['key']}", s["title"]) for s in SECTIONS]


def _photos_payload(fy):
    assets = {a.slot: a for a in ReportAsset.query.filter_by(fiscal_year_id=fy.id)}
    return {"fiscal_year": {"id": fy.id, "label": fy.label}, "slots": [{
        "slot": slot, "label": label, "photo": ({"id": a.id, "caption": a.caption or "",
                                                 "url": url_for("activity_report.photo_file", asset_id=a.id)}
                                                if (a := assets.get(slot)) else None)} for slot, label in _slots()],
        "logo_url": branding.logo_src()}


def _remove_file(relpath):
    try:
        path = os.path.join(current_app.instance_path, relpath)
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


@bp.route("/activity-report/photos")
@instance_admin_required
def activity_report_photos():
    return jsonify(_photos_payload(_fiscal_year()))


@bp.route("/activity-report/photos", methods=["POST"])
@instance_admin_required
def activity_report_photo_upload():
    """Multipart `fy_id`, `slot`, `file` : remplace la photo de l'emplacement."""
    fy = _fiscal_year(request.form.get("fy_id", type=int))
    slot = request.form.get("slot") or ""
    if slot not in {s for s, _ in _slots()}:
        raise invalid("Emplacement invalide.", "slot")
    file = request.files.get("file")
    if file is None or not file.filename:
        raise invalid("Choisissez une image.", "file")
    name = secure_filename(file.filename)
    if os.path.splitext(name)[1].lower() not in PHOTO_EXT:
        raise invalid("Format non supporté (png, jpg, webp, gif attendus).", "file")
    reldir = os.path.join("uploads", "report", str(fy.id))
    os.makedirs(os.path.join(current_app.instance_path, reldir), exist_ok=True)
    relpath = os.path.join(reldir, f"{slot}-{name}")
    file.save(os.path.join(current_app.instance_path, relpath))
    asset = ReportAsset.query.filter_by(fiscal_year_id=fy.id, slot=slot).first()
    if asset is None:
        db.session.add(ReportAsset(fiscal_year_id=fy.id, slot=slot, path=relpath))
    else:
        if asset.path != relpath:
            _remove_file(asset.path)
        asset.path = relpath
    db.session.commit()
    return jsonify(**_photos_payload(fy), notices=[notice("Photo enregistrée.")])


@bp.route("/activity-report/photos/<int:asset_id>", methods=["PATCH"])
@instance_admin_required
def activity_report_photo_caption(asset_id):
    asset = get_or_404(ReportAsset, asset_id, "Photo introuvable.")
    asset.caption = str(json_body().get("caption") or "").strip()[:300] or None
    db.session.commit()
    return jsonify(notices=[notice("Légende enregistrée.")])


@bp.route("/activity-report/photos/<int:asset_id>", methods=["DELETE"])
@instance_admin_required
def activity_report_photo_delete(asset_id):
    asset = get_or_404(ReportAsset, asset_id, "Photo introuvable.")
    _remove_file(asset.path)
    db.session.delete(asset)
    db.session.commit()
    return jsonify(notices=[notice("Photo supprimée.")])


@bp.route("/activity-report/logo", methods=["POST"])
@instance_admin_required
def activity_report_logo_upload():
    file = request.files.get("file")
    if file is None or not file.filename:
        raise invalid("Choisissez un fichier image.", "file")
    try:
        branding.save_logo(file)
    except ValueError as exc:
        raise invalid(str(exc), "file") from None
    return jsonify(logo_url=branding.logo_src(), notices=[notice("Logo de la structure enregistré.")])


@bp.route("/activity-report/logo", methods=["DELETE"])
@instance_admin_required
def activity_report_logo_delete():
    branding.delete_logo()
    return jsonify(logo_url=None, notices=[notice("Logo de la structure supprimé.")])


# ------------------------------------------------------------------ versions archivées


@bp.route("/activity-report/archives")
def activity_report_archives():
    fy = _fiscal_year()
    return jsonify(fiscal_year={"id": fy.id, "label": fy.label}, items=[{
        "id": a.id, "version": a.version, "label": a.label, "prorata": a.prorata, "created_at": _iso(a.created_at),
        "url": url_for("activity_report.archive_file", archive_id=a.id),
    } for a in ReportArchive.query.filter_by(fiscal_year_id=fy.id).order_by(ReportArchive.version.desc())])


@bp.route("/activity-report/archives", methods=["POST"])
@instance_admin_required
def activity_report_archive_create():
    data = json_body()
    fy = _fiscal_year(data.get("fy_id"))
    try:
        arc = report_pdf.create_archive(fy, prorata=bool(data.get("prorata")),
                                        label=str(data.get("label") or "").strip()[:200] or None,
                                        user_id=getattr(current_user, "id", None))
    except Exception as exc:  # génération PDF (weasyprint) en échec
        db.session.rollback()
        current_app.logger.exception("Archivage du rapport échoué")
        raise ApiError("archive_failed", f"Échec de l'archivage : {exc}", status=500) from None
    return jsonify(notices=[notice(f"Rapport archivé (version {arc.version}).")]), 201


@bp.route("/activity-report/archives/<int:archive_id>", methods=["DELETE"])
@instance_admin_required
def activity_report_archive_delete(archive_id):
    arc = get_or_404(ReportArchive, archive_id, "Version introuvable.")
    _remove_file(arc.path)
    db.session.delete(arc)
    db.session.commit()
    return jsonify(notices=[notice("Version archivée supprimée.")])
