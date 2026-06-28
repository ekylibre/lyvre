import os

from flask import (
    Blueprint, render_template, request, abort, redirect, url_for, flash,
    current_app, send_file,
)
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from app.decorators import admin_required
from app.extensions import db
from app.models import (
    FiscalYear, ReportContent, EcoDeclaration, ReportAsset, ReportArchive,
)
from app.services import activity_report_service
from app.services.activity_report_service import NARRATIVE_BLOCKS, SECTIONS
from app.services.eco_declaration_import import import_eco_xlsx
from app.services import site_content_import
from app.services import report_pdf

bp = Blueprint("activity_report", __name__, url_prefix="/rapport-activite")


def _selected_fiscal_year():
    fiscal_years = FiscalYear.query.order_by(FiscalYear.start_date.desc()).all()
    fy_id = request.args.get("fy_id", type=int)
    selected = None
    if fy_id:
        selected = next((fy for fy in fiscal_years if fy.id == fy_id), None)
    if selected is None and fiscal_years:
        selected = fiscal_years[0]
    return fiscal_years, selected


def _prorata_arg():
    """Surcharge ponctuelle du mode pro-rata via ?prorata=0|1 (sinon config)."""
    raw = request.args.get("prorata")
    if raw is None:
        return None
    return raw.lower() in ("1", "true", "yes", "on")


@bp.route("/")
@login_required
def index():
    fiscal_years, fy = _selected_fiscal_year()
    prorata = _prorata_arg()
    view = None if fy is None else activity_report_service.build_report(fy, prorata=prorata)
    return render_template(
        "activity_report/report.html",
        fiscal_years=fiscal_years, fy=fy, view=view,
        photo_srcs=report_pdf.photo_srcs(view) if view else {},
    )


@bp.route("/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit():
    fiscal_years, fy = _selected_fiscal_year()
    if fy is None:
        flash("Créez d'abord un exercice comptable.", "warning")
        return redirect(url_for("activity_report.index"))

    existing = {
        c.block_key: c
        for c in ReportContent.query.filter_by(fiscal_year_id=fy.id).all()
    }

    if request.method == "POST":
        for block_key, _label in NARRATIVE_BLOCKS:
            title = (request.form.get(f"title_{block_key}") or "").strip() or None
            body = request.form.get(f"body_{block_key}") or ""
            row = existing.get(block_key)
            if not body.strip() and title is None:
                if row is not None:
                    db.session.delete(row)
                continue
            if row is None:
                row = ReportContent(fiscal_year_id=fy.id, block_key=block_key)
                db.session.add(row)
            row.title = title
            row.body_html = body
            row.updated_by_user_id = getattr(current_user, "id", None)
        db.session.commit()
        flash("Textes du rapport enregistrés.", "success")
        return redirect(url_for("activity_report.edit", fy_id=fy.id))

    blocks = [
        {"key": key, "label": label,
         "title": (existing[key].title if key in existing else ""),
         "body": (existing[key].body_html if key in existing else "")}
        for key, label in NARRATIVE_BLOCKS
    ]
    return render_template(
        "activity_report/edit.html",
        fiscal_years=fiscal_years, fy=fy, blocks=blocks,
        site_available=site_content_import.available(),
        site_preview=site_content_import.preview() if site_content_import.available() else [],
    )


@bp.route("/edit/import-site", methods=["POST"])
@login_required
@admin_required
def import_site():
    """Pré-remplit les blocs narratifs depuis les `_data/*.yml` du site Jekyll."""
    _, fy = _selected_fiscal_year()
    if fy is None:
        flash("Créez d'abord un exercice comptable.", "warning")
        return redirect(url_for("activity_report.index"))

    overwrite = bool(request.form.get("overwrite"))
    result = site_content_import.import_site_content(fy, overwrite=overwrite)
    if result["errors"]:
        flash("Import site : " + " ; ".join(result["errors"]), "danger")
    else:
        flash(
            f"Import site : {len(result['imported'])} bloc(s) pré-rempli(s), "
            f"{len(result['skipped'])} ignoré(s).",
            "success",
        )
    return redirect(url_for("activity_report.edit", fy_id=fy.id))


@bp.route("/eco", methods=["GET", "POST"])
@login_required
@admin_required
def eco():
    """Table des tonnages éco-organismes : import xlsx + édition."""
    if request.method == "POST":
        for row in EcoDeclaration.query.all():
            if request.form.get(f"delete_{row.id}"):
                db.session.delete(row)
                continue
            entrant = (request.form.get(f"entrant_{row.id}") or "").strip().replace(",", ".")
            sortant = (request.form.get(f"sortant_{row.id}") or "").strip().replace(",", ".")
            financing = (request.form.get(f"financing_{row.id}") or "").strip().replace(",", ".")
            try:
                if entrant != "":
                    row.entrant_t = float(entrant)
                if sortant != "":
                    row.sortant_t = float(sortant)
                if financing != "":
                    row.financing_cents = int(round(float(financing) * 100))
                row.source = "manual"
            except ValueError:
                flash(f"Valeur invalide ligne {row.id} — ignorée.", "warning")
        db.session.commit()
        flash("Tonnages éco-organismes enregistrés.", "success")
        return redirect(url_for("activity_report.eco"))

    rows = EcoDeclaration.query.order_by(
        EcoDeclaration.organism, EcoDeclaration.material, EcoDeclaration.period_start
    ).all()
    return render_template("activity_report/eco.html", rows=rows)


@bp.route("/eco/import", methods=["POST"])
@login_required
@admin_required
def eco_import():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Choisissez un fichier .xlsx.", "danger")
        return redirect(url_for("activity_report.eco"))
    try:
        result = import_eco_xlsx(file.stream)
        flash(
            f"Import : {result['imported']} ligne(s) créée(s), "
            f"{result['updated']} mise(s) à jour, {len(result['errors'])} erreur(s).",
            "success" if not result["errors"] else "warning",
        )
    except Exception as e:
        flash(f"Erreur d'import : {e}", "danger")
    return redirect(url_for("activity_report.eco"))


def _photo_slots():
    """Emplacements de photo : couverture + une par section."""
    return [("cover", "Couverture")] + [
        (f"section_{s['key']}", s["title"]) for s in SECTIONS
    ]


@bp.route("/photos", methods=["GET", "POST"])
@login_required
@admin_required
def photos():
    fiscal_years, fy = _selected_fiscal_year()
    if fy is None:
        flash("Créez d'abord un exercice comptable.", "warning")
        return redirect(url_for("activity_report.index"))

    if request.method == "POST":
        # Suppressions + légendes des photos existantes.
        for a in ReportAsset.query.filter_by(fiscal_year_id=fy.id).all():
            if request.form.get(f"delete_{a.id}"):
                _remove_asset_file(a)
                db.session.delete(a)
            else:
                a.caption = (request.form.get(f"caption_{a.id}") or "").strip() or None

        # Nouvel upload (un fichier par emplacement, remplace l'existant).
        slot = (request.form.get("slot") or "").strip()
        file = request.files.get("file")
        valid_slots = {s for s, _ in _photo_slots()}
        if file and file.filename and slot in valid_slots:
            relpath = _save_photo(fy, file)
            existing = ReportAsset.query.filter_by(fiscal_year_id=fy.id, slot=slot).first()
            if existing is not None:
                _remove_asset_file(existing)
                existing.path = relpath
            else:
                db.session.add(ReportAsset(fiscal_year_id=fy.id, slot=slot, path=relpath))
        elif file and file.filename:
            flash("Emplacement invalide.", "warning")

        db.session.commit()
        flash("Photos enregistrées.", "success")
        return redirect(url_for("activity_report.photos", fy_id=fy.id))

    assets = {a.slot: a for a in ReportAsset.query.filter_by(fiscal_year_id=fy.id).all()}
    return render_template(
        "activity_report/photos.html",
        fiscal_years=fiscal_years, fy=fy, slots=_photo_slots(), assets=assets,
    )


def _save_photo(fy, file):
    reldir = os.path.join("uploads", "report", str(fy.id))
    absdir = os.path.join(current_app.instance_path, reldir)
    os.makedirs(absdir, exist_ok=True)
    fname = secure_filename(file.filename)
    file.save(os.path.join(absdir, fname))
    return os.path.join(reldir, fname)


def _remove_asset_file(asset):
    try:
        path = os.path.join(current_app.instance_path, asset.path)
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


@bp.route("/photo/<int:asset_id>")
@login_required
def photo_file(asset_id):
    asset = ReportAsset.query.get_or_404(asset_id)
    return send_file(os.path.join(current_app.instance_path, asset.path))


@bp.route("/print")
@login_required
def print_view():
    _, fy = _selected_fiscal_year()
    if fy is None:
        abort(404)
    view = activity_report_service.build_report(fy, prorata=_prorata_arg())
    return render_template(
        "activity_report/print.html", fy=fy, view=view,
        photo_srcs=report_pdf.photo_srcs(view),
    )


@bp.route("/pdf")
@login_required
def pdf_view():
    """Génère le PDF côté serveur (weasyprint) et le renvoie inline."""
    import io
    _, fy = _selected_fiscal_year()
    if fy is None:
        abort(404)
    pdf_bytes = report_pdf.build_pdf(fy, prorata=_prorata_arg())
    return send_file(
        io.BytesIO(pdf_bytes), mimetype="application/pdf",
        as_attachment=False, download_name=f"rapport-activite-{fy.label}.pdf",
    )


@bp.route("/archive", methods=["POST"])
@login_required
@admin_required
def archive_create():
    """Fige une version PDF consultable du rapport de l'exercice sélectionné."""
    _, fy = _selected_fiscal_year()
    if fy is None:
        flash("Créez d'abord un exercice comptable.", "warning")
        return redirect(url_for("activity_report.index"))
    label = (request.form.get("label") or "").strip() or None
    try:
        arc = report_pdf.create_archive(
            fy, prorata=_prorata_arg(), label=label,
            user_id=getattr(current_user, "id", None),
        )
        flash(f"Rapport archivé (version {arc.version}).", "success")
    except Exception as e:
        flash(f"Échec de l'archivage : {e}", "danger")
    return redirect(url_for("activity_report.archives", fy_id=fy.id))


@bp.route("/archives")
@login_required
def archives():
    fiscal_years, fy = _selected_fiscal_year()
    items = []
    if fy is not None:
        items = (ReportArchive.query.filter_by(fiscal_year_id=fy.id)
                 .order_by(ReportArchive.version.desc()).all())
    return render_template(
        "activity_report/archives.html",
        fiscal_years=fiscal_years, fy=fy, archives=items,
    )


@bp.route("/archive/<int:archive_id>")
@login_required
def archive_file(archive_id):
    arc = ReportArchive.query.get_or_404(archive_id)
    path = os.path.join(current_app.instance_path, arc.path)
    if not os.path.isfile(path):
        abort(404)
    name = f"rapport-activite-{arc.fiscal_year.label}-v{arc.version}.pdf"
    return send_file(path, mimetype="application/pdf", download_name=name)


@bp.route("/archive/<int:archive_id>/delete", methods=["POST"])
@login_required
@admin_required
def archive_delete(archive_id):
    arc = ReportArchive.query.get_or_404(archive_id)
    fy_id = arc.fiscal_year_id
    try:
        path = os.path.join(current_app.instance_path, arc.path)
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass
    db.session.delete(arc)
    db.session.commit()
    flash("Version archivée supprimée.", "success")
    return redirect(url_for("activity_report.archives", fy_id=fy_id))
