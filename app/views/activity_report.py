"""Rapport d'activité : fichiers servis par Flask (écrans : SPA, API : app/api/activity_report.py).
Aperçu HTML autonome (iframe de la SPA), PDF (weasyprint, inchangé), exports HTML / DOCX / ODT,
photos, logo et versions archivées."""
import io
import os

from flask import Blueprint, abort, current_app, request, send_file
from flask_login import login_required

from app.models import FiscalYear, ReportArchive, ReportAsset
from app.services import activity_report_service, branding, report_export, report_pdf

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


@bp.route("/apercu")
@login_required
def preview():
    """Rapport en HTML autonome (graphes SVG, sans script) pour l'aperçu de la SPA."""
    _, fy = _selected_fiscal_year()
    if fy is None:
        abort(404)
    response = current_app.response_class(report_export.build_html(fy, prorata=_prorata_arg()),
                                          mimetype="text/html")
    # Contenu saisi par les administrateurs (HTML) : aucun script exécuté dans l'aperçu.
    response.headers["Content-Security-Policy"] = "script-src 'none'; frame-ancestors 'self'"
    return response


@bp.route("/photo/<int:asset_id>")
@login_required
def photo_file(asset_id):
    asset = ReportAsset.query.get_or_404(asset_id)
    path = os.path.join(current_app.instance_path, asset.path)
    if not os.path.isfile(path):
        abort(404)
    return send_file(path)


@bp.route("/logo-file")
@login_required
def logo_file():
    path = branding.logo_abspath()
    if not path or not os.path.isfile(path):
        abort(404)
    return send_file(path)


@bp.route("/pdf")
@login_required
def pdf_view():
    """Génère le PDF côté serveur (weasyprint) et le renvoie inline."""
    _, fy = _selected_fiscal_year()
    if fy is None:
        abort(404)
    pdf_bytes = report_pdf.build_pdf(fy, prorata=_prorata_arg())
    return send_file(
        io.BytesIO(pdf_bytes), mimetype="application/pdf",
        as_attachment=False, download_name=f"rapport-activite-{fy.label}.pdf",
    )


# Exports « ensemble du rapport » (avec styles) : HTML autonome, DOCX, ODT.
@bp.route("/export/<fmt>")
@login_required
def export_view(fmt):
    """Exporte tout le rapport en HTML autonome, DOCX ou ODT (styles inclus)."""
    _, fy = _selected_fiscal_year()
    if fy is None:
        abort(404)
    view = activity_report_service.build_report(fy, prorata=_prorata_arg())
    base = f"rapport-activite-{fy.label}"

    if fmt == "html":
        data = report_export.build_html(fy, view=view).encode("utf-8")
        mime = "text/html; charset=utf-8"
    elif fmt == "docx":
        data = report_export.build_docx(fy, view=view)
        mime = ("application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document")
    elif fmt == "odt":
        data = report_export.build_odt(fy, view=view)
        mime = "application/vnd.oasis.opendocument.text"
    else:
        abort(404)

    return send_file(
        io.BytesIO(data), mimetype=mime,
        as_attachment=True, download_name=f"{base}.{fmt}",
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
