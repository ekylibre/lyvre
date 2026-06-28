"""Génération du PDF du rapport d'activité côté serveur (weasyprint).

Sert l'export PDF sans navigateur (utile pour l'archivage et l'envoi). weasyprint
n'exécutant pas de JS, les graphes ECharts sont rendus en **SVG** (`chart_svg`),
et les photos uploadées sont résolues en chemins `file://` (l'endpoint
`photo_file` est protégé par authentification, donc non récupérable par weasyprint).
Les logos/photos importés du site restent en URL absolue (récupérés en HTTP).
"""
import os

from flask import current_app, render_template, url_for

from app.services import activity_report_service, chart_svg, branding


def photo_srcs(view, pdf=False):
    """Map asset_id -> URL d'affichage de la photo, selon le mode de rendu.

    - HTML (écran/impression navigateur) : endpoint `photo_file` (servi par Flask) ;
    - PDF (weasyprint) : chemin `file://` absolu lu directement sur le disque."""
    assets = []
    if view.cover.get("photo_asset"):
        assets.append(view.cover["photo_asset"])
    for s in view.sections:
        if s.photo:
            assets.append(s.photo)

    srcs = {}
    for a in assets:
        if pdf:
            srcs[a.id] = "file://" + os.path.join(current_app.instance_path, a.path)
        else:
            srcs[a.id] = url_for("activity_report.photo_file", asset_id=a.id)
    return srcs


def build_pdf(fy, prorata=None, view=None):
    """Rend le rapport de l'exercice `fy` en PDF (bytes)."""
    from weasyprint import HTML, CSS

    if view is None:
        view = activity_report_service.build_report(fy, prorata=prorata)
    chart_svgs = {cid: chart_svg.option_to_svg(opt) for cid, opt in view.charts.items()}
    html = render_template(
        "activity_report/pdf.html",
        fy=fy, view=view, pdf=True,
        chart_svgs=chart_svgs, photo_srcs=photo_srcs(view, pdf=True),
        structure_logo=branding.logo_src(pdf=True),
    )
    css_path = os.path.join(current_app.static_folder, "css", "report.css")
    return HTML(string=html, base_url=current_app.instance_path).write_pdf(
        stylesheets=[CSS(filename=css_path)]
    )


def create_archive(fy, prorata=None, label=None, user_id=None):
    """Fige le rapport courant en PDF et enregistre une nouvelle version archivée."""
    from app.extensions import db
    from app.models import ReportArchive

    view = activity_report_service.build_report(fy, prorata=prorata)
    pdf = build_pdf(fy, view=view)

    last = (ReportArchive.query
            .filter_by(fiscal_year_id=fy.id)
            .order_by(ReportArchive.version.desc())
            .first())
    version = (last.version + 1) if last else 1

    reldir = os.path.join("uploads", "report", str(fy.id), "archives")
    absdir = os.path.join(current_app.instance_path, reldir)
    os.makedirs(absdir, exist_ok=True)
    relpath = os.path.join(reldir, f"v{version}.pdf")
    with open(os.path.join(current_app.instance_path, relpath), "wb") as fh:
        fh.write(pdf)

    arc = ReportArchive(
        fiscal_year_id=fy.id, version=version, label=(label or None),
        path=relpath, prorata=view.prorata, created_by_user_id=user_id,
    )
    db.session.add(arc)
    db.session.commit()
    return arc
