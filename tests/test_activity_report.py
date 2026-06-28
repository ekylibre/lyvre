"""Tests du rapport d'activité : import éco-organismes, impact, synthèse
financière, contenus narratifs, assemblage."""
import io
from datetime import date

import pytest
from openpyxl import Workbook

from app.extensions import db
from app.models import (
    FiscalYear, ReportContent, EcoDeclaration, ReportArchive,
    Account, Journal, JournalEntry, JournalLine,
)
from app.services import activity_report_service as ars
from app.services import site_content_import
from app.services.eco_declaration_import import import_eco_xlsx


def _bilan_xlsx():
    """Construit un .xlsx 'Bilan' synthétique calqué sur la déclaration réelle."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Bilan"
    rows = [
        ["", "", "", "T2 2025", "T3 2025"],
        ["Ecomaison", "Meubles", "Entrant", 10, 5],
        ["", "", "Sortant", 4, 2],
        ["Ecologic", "D3E", "Entrant", 2, 1],
        ["", "", "Sortant", 1, 0.5],
        ["", "", "", "", ""],
        ["", "Volumes", "Entrant", 12, 6],      # doit être EXCLU
        ["", "", "Sortant", 5, 2.5],
        ["", "Facturation", "Ecologic", 100, 200],
        ["", "", "Ecomaison", 1000, 800],
        ["", "", "TOTAL", 1100, 1000],
    ]
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _fy_2025():
    fy = FiscalYear(label="2025", start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    db.session.add(fy)
    db.session.commit()
    return fy


# --- import éco-organismes ------------------------------------------------


def test_eco_import_parses_materials_and_financing(session):
    result = import_eco_xlsx(_bilan_xlsx())
    assert result["errors"] == []

    materials = {r.material for r in EcoDeclaration.query.all()}
    assert "Meubles" in materials and "D3E" in materials
    assert "Volumes" not in materials             # totaux exclus
    assert "Facturation" in materials

    meubles = EcoDeclaration.query.filter_by(material="Meubles", quarter_label="T2 2025").first()
    assert float(meubles.entrant_t) == 10 and float(meubles.sortant_t) == 4

    # Facturation pour les DEUX organismes (label + organisme même ligne).
    eco_fin = EcoDeclaration.query.filter_by(material="Facturation", organism="ecologic").all()
    maison_fin = EcoDeclaration.query.filter_by(material="Facturation", organism="ecomaison").all()
    assert sum(r.financing_cents for r in eco_fin) == 30000      # (100+200) €
    assert sum(r.financing_cents for r in maison_fin) == 180000  # (1000+800) €


def test_eco_import_idempotent(session):
    import_eco_xlsx(_bilan_xlsx())
    n1 = EcoDeclaration.query.count()
    res = import_eco_xlsx(_bilan_xlsx())
    assert EcoDeclaration.query.count() == n1   # upsert, pas de doublon
    assert res["updated"] > 0


# --- impact éco -----------------------------------------------------------


def test_eco_impact_aggregation(session):
    fy = _fy_2025()
    import_eco_xlsx(_bilan_xlsx())
    eco = ars.eco_impact(fy)
    assert eco["has_data"] is True
    assert eco["collecte_t"] == pytest.approx(18.0)    # 10+5+2+1
    assert eco["reemploye_t"] == pytest.approx(7.5)    # 4+2+1+0.5
    assert eco["reuse_rate"] == pytest.approx(7.5 / 18)
    assert eco["financing_cents"] == 210000            # 300 + 1800 €


def test_eco_impact_co2_uses_default_factors(session):
    fy = _fy_2025()
    import_eco_xlsx(_bilan_xlsx())
    eco = ars.eco_impact(fy)
    # Meubles sortant 6 t × 1200 + D3E sortant 1,5 t × 3000 = 7200 + 4500
    assert eco["co2e_avoided_kg"] == pytest.approx(11700.0)


def test_eco_impact_indivisible_excludes_quarter_started_outside(session):
    """Mode indivisible (défaut) : un trimestre dont la date de début est hors
    exercice est totalement exclu, même s'il chevauche l'exercice."""
    # Exercice 2025-02-01 → 2026-01-31 : le T1 2025 (début 2025-01-01) est exclu.
    fy = FiscalYear(label="2025/26", start_date=date(2025, 2, 1), end_date=date(2026, 1, 31))
    db.session.add(fy)
    db.session.add(EcoDeclaration(
        organism="ecomaison", material="Meubles", quarter_label="T1 2025",
        period_start=date(2025, 1, 1), entrant_t=90, sortant_t=30, financing_cents=0,
    ))
    db.session.commit()

    eco = ars.eco_impact(fy, prorata=False)
    assert eco["has_data"] is False
    assert eco["collecte_t"] == 0


def test_eco_impact_prorata_splits_boundary_quarter(session):
    """Mode pro-rata : le T1 2025 (90 j, dont 59 dans l'exercice 02/2025→01/2026)
    est pris à 59/90."""
    fy = FiscalYear(label="2025/26", start_date=date(2025, 2, 1), end_date=date(2026, 1, 31))
    db.session.add(fy)
    db.session.add_all([
        EcoDeclaration(
            organism="ecomaison", material="Meubles", quarter_label="T1 2025",
            period_start=date(2025, 1, 1), entrant_t=90, sortant_t=30, financing_cents=0,
        ),
        EcoDeclaration(
            organism="ecomaison", material="Facturation", quarter_label="T1 2025",
            period_start=date(2025, 1, 1), entrant_t=0, sortant_t=0, financing_cents=9000,
        ),
    ])
    db.session.commit()

    frac = 59 / 90  # févr.+mars = 28+31 jours inclus, sur 90 jours (janv.→mars)
    eco = ars.eco_impact(fy, prorata=True)
    assert eco["prorata"] is True
    assert eco["has_data"] is True
    assert eco["collecte_t"] == pytest.approx(round(90 * frac, 3))
    assert eco["reemploye_t"] == pytest.approx(round(30 * frac, 3))
    assert eco["financing_cents"] == int(round(9000 * frac))


def test_eco_impact_prorata_full_quarter_unchanged(session):
    """Un trimestre entièrement dans l'exercice n'est pas modifié par le pro-rata."""
    fy = _fy_2025()
    db.session.add(EcoDeclaration(
        organism="ecomaison", material="Meubles", quarter_label="T2 2025",
        period_start=date(2025, 4, 1), entrant_t=10, sortant_t=4, financing_cents=0,
    ))
    db.session.commit()
    assert ars.eco_impact(fy, prorata=True)["collecte_t"] == pytest.approx(10)
    assert ars.eco_impact(fy, prorata=False)["collecte_t"] == pytest.approx(10)


# --- contenus narratifs ---------------------------------------------------


def test_report_content_rendered_in_build(session):
    fy = _fy_2025()
    db.session.add(ReportContent(
        fiscal_year_id=fy.id, block_key="edito",
        title="Le mot du bureau", body_html="<p>Bonjour</p>",
    ))
    db.session.commit()
    view = ars.build_report(fy)
    edito = next(s for s in view.sections if s.key == "edito")
    assert edito.narrative and edito.narrative[0]["title"] == "Le mot du bureau"


# --- assemblage -----------------------------------------------------------


def test_build_report_structure(session):
    fy = _fy_2025()
    import_eco_xlsx(_bilan_xlsx())
    view = ars.build_report(fy)
    assert len(view.sections) == 10
    assert view.cover["year_label"] == "2025"
    reemploi = next(s for s in view.sections if s.key == "reemploi")
    assert reemploi.eco is not None and reemploi.eco["has_data"]
    assert "chart-tonnages" in reemploi.charts


def test_build_pdf_server_side(session):
    """PDF serveur weasyprint : produit un PDF non vide, charts éco en SVG."""
    from app.services import report_pdf
    fy = _fy_2025()
    db.session.add(ReportContent(
        fiscal_year_id=fy.id, block_key="edito",
        title="Édito", body_html="<p>Bonjour</p>",
    ))
    db.session.commit()
    import_eco_xlsx(_bilan_xlsx())   # alimente la section impact (+ chart-tonnages)

    view = ars.build_report(fy)
    assert "chart-tonnages" in view.charts          # un graphe à rendre en SVG
    pdf = report_pdf.build_pdf(fy, view=view)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 2000


def test_create_and_version_archive(app, session, tmp_path):
    """Archivage : fige un PDF versionné par exercice, incrémente la version."""
    import os
    from app.services import report_pdf
    app.instance_path = str(tmp_path)

    fy = _fy_2025()
    db.session.add(ReportContent(
        fiscal_year_id=fy.id, block_key="edito", title="É", body_html="<p>x</p>"))
    db.session.commit()

    a1 = report_pdf.create_archive(fy, label="Validé en AG")
    assert a1.version == 1 and a1.prorata is False and a1.label == "Validé en AG"
    fpath = os.path.join(str(tmp_path), a1.path)
    assert os.path.isfile(fpath)
    with open(fpath, "rb") as fh:
        assert fh.read(4) == b"%PDF"

    a2 = report_pdf.create_archive(fy)                 # version suivante
    assert a2.version == 2
    a3 = report_pdf.create_archive(fy, prorata=True)   # mode pro-rata mémorisé
    assert a3.version == 3 and a3.prorata is True

    assert ReportArchive.query.filter_by(fiscal_year_id=fy.id).count() == 3


def test_branding_logo_roundtrip(app, tmp_path):
    """Logo de structure : upload, détection, remplacement sans doublon, suppression."""
    import glob
    import io as _io
    import os
    from werkzeug.datastructures import FileStorage
    from app.services import branding
    app.instance_path = str(tmp_path)

    assert branding.logo_relpath() is None
    branding.save_logo(FileStorage(stream=_io.BytesIO(b"\x89PNG\r\n"), filename="mon-logo.png"))
    rel = branding.logo_relpath()
    assert rel and rel.endswith("logo.png")
    assert os.path.isfile(branding.logo_abspath())
    assert branding.logo_src(pdf=True).startswith("file://")
    with app.test_request_context():
        assert "/rapport-activite/logo-file" in branding.logo_src(pdf=False)

    # Remplacer par une autre extension ne laisse pas de doublon.
    branding.save_logo(FileStorage(stream=_io.BytesIO(b"<svg/>"), filename="x.svg"))
    found = glob.glob(os.path.join(str(tmp_path), "uploads", "branding", "logo.*"))
    assert len(found) == 1 and found[0].endswith("logo.svg")

    branding.delete_logo()
    assert branding.logo_relpath() is None


def test_branding_rejects_bad_extension(app, tmp_path):
    import io as _io
    from werkzeug.datastructures import FileStorage
    from app.services import branding
    app.instance_path = str(tmp_path)
    with pytest.raises(ValueError):
        branding.save_logo(FileStorage(stream=_io.BytesIO(b"x"), filename="logo.txt"))


def test_uploaded_logo_used_in_report(app, session, tmp_path):
    """Le logo uploadé remplace le pictogramme SVG dans le rendu du rapport."""
    import io as _io
    from werkzeug.datastructures import FileStorage
    from flask import render_template
    from app.services import branding
    app.instance_path = str(tmp_path)

    fy = _fy_2025()
    branding.save_logo(FileStorage(stream=_io.BytesIO(b"\x89PNG\r\n"), filename="logo.png"))
    view = ars.build_report(fy)
    html = render_template(
        "activity_report/pdf.html", fy=fy, view=view, pdf=True,
        chart_svgs={}, photo_srcs={}, structure_logo=branding.logo_src(pdf=True),
    )
    assert 'class="brand-logo' in html         # logo uploadé
    assert "<svg class=\"sn-logo" not in html  # plus le pictogramme par défaut
    assert "file://" in html and "logo.png" in html


def test_period_for_fiscal_year(session):
    fy = _fy_2025()
    p = ars.dashboard_service.period_for_fiscal_year(fy)
    assert p.start == date(2025, 1, 1) and p.end == date(2026, 1, 1)


# --- synthèse financière (pas de double comptage) -------------------------


def test_financial_summary_no_double_count(session):
    fy = _fy_2025()
    a7 = Account(code="701", label="Ventes")
    a6 = Account(code="607", label="Achats")
    jr = Journal(code="OD", label="OD")
    db.session.add_all([a7, a6, jr])
    db.session.commit()
    e = JournalEntry(fiscal_year_id=fy.id, journal_id=jr.id, entry_date=date(2025, 6, 1))
    db.session.add(e)
    db.session.flush()
    db.session.add_all([
        JournalLine(entry_id=e.id, account_id=a7.id, credit_cents=1000000),
        JournalLine(entry_id=e.id, account_id=a6.id, debit_cents=600000),
    ])
    db.session.commit()

    fs = ars.financial_summary(fy)
    lines = {l["label"]: l for l in fs["lines"]}
    # 607 ne doit PAS être compté à la fois dans "achats" et "autres achats 60".
    assert lines["Charges d'exploitation"]["n"] == 600000
    assert lines["Produits d'exploitation"]["n"] == 1000000
    assert fs["result_net_cents"] == 400000


# --- import contenus du site (_data/*.yml) --------------------------------


def _seed_site_data(app, tmp_path):
    """Crée un dossier _data minimal et le pointe via la config."""
    import yaml as _yaml

    data = {
        "partners.yml": [
            {"name": "Mairie", "description": "Soutien local.", "link": "https://m.fr"},
            {"name": "ADEME", "description": "Transition <écologique>."},
        ],
        "infos.yml": [
            {"name": "Julien", "content": "Président"},
            {"name": "David", "content": "Trésorier"},
        ],
        "missions.yml": [{"name": "Collecter", "description": "On collecte."}],
        "services.yml": [{"name": "Repair Café", "description": "On répare."}],
    }
    for fname, items in data.items():
        (tmp_path / fname).write_text(_yaml.safe_dump(items, allow_unicode=True))
    app.config["SITE_DATA_PATH"] = str(tmp_path)


def test_site_import_prefills_blocks(app, session, tmp_path):
    _seed_site_data(app, tmp_path)
    fy = _fy_2025()

    assert site_content_import.available() is True
    result = site_content_import.import_site_content(fy)
    assert result["errors"] == []
    assert set(result["imported"]) == {
        "partenaires", "gouvernance", "intro_reemploi", "intro_boutique"
    }

    partenaires = ReportContent.query.filter_by(
        fiscal_year_id=fy.id, block_key="partenaires"
    ).first()
    assert "Mairie" in partenaires.body_html
    assert 'href="https://m.fr"' in partenaires.body_html
    # Le HTML dangereux des descriptions est échappé.
    assert "<écologique>" not in partenaires.body_html
    assert "&lt;" in partenaires.body_html

    gouvernance = ReportContent.query.filter_by(
        fiscal_year_id=fy.id, block_key="gouvernance"
    ).first()
    assert "Julien" in gouvernance.body_html and "Président" in gouvernance.body_html


def test_site_import_respects_existing_unless_overwrite(app, session, tmp_path):
    _seed_site_data(app, tmp_path)
    fy = _fy_2025()
    db.session.add(ReportContent(
        fiscal_year_id=fy.id, block_key="partenaires",
        title="Mes partenaires", body_html="<p>Texte maison</p>",
    ))
    db.session.commit()

    r1 = site_content_import.import_site_content(fy)
    assert "partenaires" in r1["skipped"] and "partenaires" not in r1["imported"]
    kept = ReportContent.query.filter_by(
        fiscal_year_id=fy.id, block_key="partenaires"
    ).first()
    assert kept.body_html == "<p>Texte maison</p>"

    r2 = site_content_import.import_site_content(fy, overwrite=True)
    assert "partenaires" in r2["imported"]
    overwritten = ReportContent.query.filter_by(
        fiscal_year_id=fy.id, block_key="partenaires"
    ).first()
    assert "Mairie" in overwritten.body_html
    assert overwritten.title == "Mes partenaires"   # titre existant préservé


def test_site_import_unavailable_path(app, session, tmp_path):
    app.config["SITE_DATA_PATH"] = str(tmp_path / "does-not-exist")
    fy = _fy_2025()
    assert site_content_import.available() is False
    result = site_content_import.import_site_content(fy)
    assert result["imported"] == [] and result["errors"]


def test_raw_data_base_url_variants():
    f = site_content_import._raw_data_base
    expected = "https://raw.githubusercontent.com/o/r/main/_data"
    assert f("https://github.com/o/r/tree/main/") == expected
    assert f("https://github.com/o/r/tree/main/_data") == expected
    assert f("https://raw.githubusercontent.com/o/r/main/_data") == expected


def test_site_import_remote_github(app, session, monkeypatch):
    """Source distante : lecture des _data/*.yml via raw.githubusercontent.com."""
    import yaml as _yaml

    app.config["SITE_DATA_PATH"] = (
        "https://github.com/asso-seconde-nature/seconde-nature.github.io/tree/main/"
    )
    fy = _fy_2025()

    files = {
        "partners.yml": [{"name": "Mairie", "description": "Soutien.",
                          "link": "https://m.fr", "image": "/assets/img/mairie.png"}],
        "infos.yml": [{"name": "Julien", "content": "Président",
                       "image": "/assets/img/julien.jpeg"}],
        "missions.yml": [{"name": "Collecter", "description": "On collecte."}],
        "services.yml": [{"name": "Repair", "description": "On répare."}],
    }
    seen = []

    class _Resp:
        status_code = 200

        def __init__(self, text):
            self.text = text

        def raise_for_status(self):
            pass

    def fake_get(url, timeout=None):
        seen.append(url)
        return _Resp(_yaml.safe_dump(files[url.rsplit("/", 1)[-1]], allow_unicode=True))

    monkeypatch.setattr(site_content_import.requests, "get", fake_get)

    assert site_content_import.available() is True   # pas d'appel réseau
    result = site_content_import.import_site_content(fy)
    assert result["errors"] == []
    assert set(result["imported"]) == {
        "partenaires", "gouvernance", "intro_reemploi", "intro_boutique"
    }
    assert (
        "https://raw.githubusercontent.com/asso-seconde-nature/"
        "seconde-nature.github.io/main/_data/partners.yml"
    ) in seen
    p = ReportContent.query.filter_by(
        fiscal_year_id=fy.id, block_key="partenaires"
    ).first()
    assert "Mairie" in p.body_html and 'href="https://m.fr"' in p.body_html
    # Logo résolu en URL raw absolue (racine du dépôt, pas _data).
    assert ('<img class="partner-logo" src="https://raw.githubusercontent.com/'
            "asso-seconde-nature/seconde-nature.github.io/main/assets/img/mairie.png"
            '"') in p.body_html

    # Photo des membres de la gouvernance résolue de la même façon.
    g = ReportContent.query.filter_by(
        fiscal_year_id=fy.id, block_key="gouvernance"
    ).first()
    assert ('<img class="team-photo" src="https://raw.githubusercontent.com/'
            "asso-seconde-nature/seconde-nature.github.io/main/assets/img/julien.jpeg"
            '"') in g.body_html
