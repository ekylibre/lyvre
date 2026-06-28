"""Export du rapport d'activité en HTML autonome, DOCX et ODT.

Construit un HTML *self-contained* (CSS inliné, variables CSS résolues en valeurs
littérales, images en data-URI, graphes ECharts en SVG) servant les trois formats :
HTML tel quel, DOCX/ODT via LibreOffice headless (`soffice --convert-to`).

Réutilise le corps de rapport partagé (`_body.html`, mode `pdf=True` : pas de JS,
graphes en SVG). Le HTML conserve fidèlement la mise en page ; DOCX/ODT sont une
conversion *best-effort* par LibreOffice (flexbox/polices web approximés).
"""
import base64
import os
import re
import subprocess
import tempfile
from shutil import which

from flask import current_app, render_template

from app.services import activity_report_service, chart_svg, branding


_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
}


def _data_uri(abspath):
    ext = os.path.splitext(abspath)[1].lower()
    mime = _MIME.get(ext, "application/octet-stream")
    with open(abspath, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _photo_data_uris(view):
    """Map asset_id -> data-URI (HTML autonome, sans dépendance réseau/disque)."""
    assets = []
    if view.cover.get("photo_asset"):
        assets.append(view.cover["photo_asset"])
    for s in view.sections:
        if s.photo:
            assets.append(s.photo)

    srcs = {}
    for a in assets:
        abspath = os.path.join(current_app.instance_path, a.path)
        if os.path.isfile(abspath):
            srcs[a.id] = _data_uri(abspath)
    return srcs


def _logo_data_uri():
    abspath = branding.logo_abspath()
    if abspath and os.path.isfile(abspath):
        return _data_uri(abspath)
    return None


def _resolve_css_vars(css):
    """Remplace `var(--x)` par sa valeur littérale.

    LibreOffice (import HTML) ne gère pas les custom properties CSS : on inline
    leurs valeurs pour préserver couleurs et tokens dans DOCX/ODT. Les variables
    du rapport sont déclarées dans le bloc `.report { --x: … }`."""
    declared = dict(re.findall(r"--([\w-]+)\s*:\s*([^;{}]+);", css))

    def repl(m):
        name = m.group(1).strip()
        fallback = (m.group(2) or "").strip()
        val = declared.get(name)
        return val.strip() if val is not None else (fallback or "inherit")

    return re.sub(r"var\(\s*--([\w-]+)\s*(?:,([^()]*))?\)", repl, css)


def _inline_css():
    path = os.path.join(current_app.static_folder, "css", "report.css")
    with open(path, encoding="utf-8") as fh:
        return _resolve_css_vars(fh.read())


def build_html(fy, prorata=None, view=None):
    """HTML autonome du rapport (CSS inliné, images en data-URI, graphes SVG)."""
    if view is None:
        view = activity_report_service.build_report(fy, prorata=prorata)
    chart_svgs = {cid: chart_svg.option_to_svg(opt) for cid, opt in view.charts.items()}
    return render_template(
        "activity_report/export.html",
        fy=fy, view=view, pdf=True,
        chart_svgs=chart_svgs,
        photo_srcs=_photo_data_uris(view),
        structure_logo=_logo_data_uri(),
        inline_css=_inline_css(),
    )


def _soffice_bin():
    return which("soffice") or which("libreoffice") or "soffice"


# Filtre de sortie LibreOffice par format cible.
_OUT_FILTER = {"docx": "MS Word 2007 XML", "odt": "writer8"}


def _soffice_convert(html, fmt):
    """Convertit un HTML en `fmt` (« docx »/« odt ») via LibreOffice → bytes."""
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "rapport.html")
        with open(src, "w", encoding="utf-8") as fh:
            fh.write(html)
        # Profil LibreOffice dédié et HOME isolé : évite tout conflit avec une
        # instance déjà ouverte sur la machine.
        profile = os.path.join(d, "profile")
        # `--infilter="HTML (StarWriter)"` force l'import en document Writer
        # (et non « Writer/Web », qui n'a pas de filtre d'export docx/odt).
        cmd = [
            _soffice_bin(), "--headless", "--norestore", "--nologo",
            f"-env:UserInstallation=file://{profile}",
            "--infilter=HTML (StarWriter)",
            "--convert-to", f"{fmt}:{_OUT_FILTER[fmt]}", "--outdir", d, src,
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=180,
                       env={**os.environ, "HOME": d})
        out = os.path.join(d, "rapport." + fmt)
        with open(out, "rb") as fh:
            return fh.read()


def build_docx(fy, prorata=None, view=None):
    return _soffice_convert(build_html(fy, prorata=prorata, view=view), "docx")


def build_odt(fy, prorata=None, view=None):
    return _soffice_convert(build_html(fy, prorata=prorata, view=view), "odt")
