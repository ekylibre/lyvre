"""Tests des évolutions : sélecteur de relance + aperçu du gabarit."""
from datetime import date

from flask import render_template

from app.views.entities import _sample_expired_row
from app.services import membership_reminders as mr
from app.models.email_template import (
    EmailTemplate, DEFAULT_REMINDER_SUBJECT, DEFAULT_REMINDER_BODY,
)


def test_templates_compile(app):
    for t in (
        "entities/reminder_preview.html",
        "entities/reminder_template_form.html",
    ):
        app.jinja_env.get_template(t)


def test_sample_expired_row_fallback_when_empty(app):
    # Base de test vide -> aucun adhérent expiré -> exemple fictif.
    with app.test_request_context("/entities/members/reminder-template"):
        row, is_real = _sample_expired_row()
    assert is_real is False
    assert row["color"] == "red"
    assert row["name"] and row["email"]
    assert isinstance(row["birthday"], date)


def test_preview_renders_member_data(app):
    sample, _ = (
        {
            "name": "Marie Curie", "email": "marie@example.org",
            "birthday": date(2026, 3, 1), "status": "ok", "color": "red",
            "label": "ok", "css": "bg-danger", "entity": None,
        },
        False,
    )
    tpl = EmailTemplate(subject=DEFAULT_REMINDER_SUBJECT, body_html=DEFAULT_REMINDER_BODY)
    subject, body = mr.render_reminder(tpl, sample, "https://helloasso.test/renew")
    assert subject == DEFAULT_REMINDER_SUBJECT
    assert "Marie Curie" in body
    assert "01/03/2026" in body
    assert 'href="https://helloasso.test/renew"' in body


def test_template_form_page_renders(app):
    """Le template d'édition se rend sans erreur avec le contexte d'aperçu."""
    sample = {
        "name": "Test User", "email": "t@u.fr", "birthday": date(2026, 1, 1),
        "status": "ok", "color": "red", "label": "ok", "css": "bg-danger",
        "entity": None,
    }
    with app.test_request_context():
        html = render_template(
            "entities/reminder_template_form.html",
            subject="Sujet {{ nom }}",
            body_html="<p>{{ nom }}</p>",
            preview_subject="Sujet Test User",
            preview_body="<p>Test User</p>",
            preview_error=None,
            sample_row=sample,
            sample_is_real=False,
            helloasso_url="https://x.test",
        )
    assert "Aperçu" in html
    assert "srcdoc" in html
    assert "Exemple fictif" in html  # badge données fictives


def test_template_form_has_wysiwyg_editor(app):
    """L'éditeur Quill et le champ soumis body_html sont présents et corrects."""
    sample = {
        "name": "Test", "email": "t@u.fr", "birthday": date(2026, 1, 1),
        "status": "ok", "color": "red", "label": "ok", "css": "bg-danger",
        "entity": None,
    }
    with app.test_request_context():
        html = render_template(
            "entities/reminder_template_form.html",
            subject="s", body_html='<p>Bonjour {{ nom }}</p>',
            preview_subject="s", preview_body="<p>x</p>",
            preview_error=None, sample_row=sample, sample_is_real=False,
            helloasso_url="https://x.test",
        )
    # Quill chargé depuis le CDN + conteneur éditeur
    assert "quill@2" in html
    assert 'id="editor"' in html
    # Le champ réellement soumis reste body_html (hidden, alimenté par Quill)
    assert 'name="body_html"' in html and 'id="body-field"' in html
    # Les placeholders Jinja sont rendus littéralement dans les boutons/data
    assert 'data-insert="{{ nom }}"' in html
    assert 'data-link="{{ lien_helloasso }}"' in html
    # Le corps initial est injecté dans le panneau code source
    assert "Bonjour {{ nom }}" in html


def test_template_form_shows_real_data_badge(app):
    sample = {
        "name": "Réel Adhérent", "email": "r@a.fr", "birthday": date(2026, 1, 1),
        "status": "ok", "color": "red", "label": "ok", "css": "bg-danger",
        "entity": None,
    }
    with app.test_request_context():
        html = render_template(
            "entities/reminder_template_form.html",
            subject="s", body_html="<p>x</p>",
            preview_subject="s", preview_body="<p>x</p>",
            preview_error=None,
            sample_row=sample, sample_is_real=True,
            helloasso_url="https://x.test",
        )
    assert "Données réelles : Réel Adhérent" in html


def test_template_form_renders_preview_error(app):
    with app.test_request_context():
        html = render_template(
            "entities/reminder_template_form.html",
            subject="s", body_html="{{ bad",
            preview_subject="", preview_body="",
            preview_error="unexpected end of template",
            sample_row={"name": "x", "email": "y", "birthday": date(2026, 1, 1),
                        "color": "red", "label": "ok", "css": "bg-danger"},
            sample_is_real=False,
            helloasso_url="",
        )
    assert "Erreur de rendu" in html
