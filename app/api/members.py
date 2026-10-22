"""Adhérents : liste (statut d'adhésion), actions groupées, relances par email et
gabarit du message. Les exports restent des fichiers servis par Flask
(`entities.members_export`)."""
from datetime import date, timedelta

from flask import current_app, jsonify, request, url_for

from app.extensions import db
from app.models import EmailTemplate, Entity
from app.models.email_template import (
    DEFAULT_REMINDER_BODY, DEFAULT_REMINDER_SUBJECT, MEMBERSHIP_REMINDER_KEY,
)
from app.queries.entities import member_rows
from app.services import external_config, membership_reminders, odoo_partner_update
from app.services.odoo_client import OdooConfigError

from . import ApiError, bp, invalid, json_body, notice
from .entities import integrations_state

FILTER_KEYS = ("q", "date_from", "date_to", "sort_by", "sort")
STATUS_LABELS = {"ok": "À jour (HelloAsso)", "asha": "Caisse seulement", "?": "Inconnu"}


def _iso(value):
    return value.isoformat() if value else None


def member_payload(row) -> dict:
    return {
        "id": row["entity"].id if row.get("entity") is not None else None,
        "name": row["name"], "email": row["email"], "is_member": row["is_member"],
        "is_benevole": row["is_benevole"], "notes": row["notes"],
        "last_helloasso_membership": _iso(row["last_ha"]), "last_pos_membership": _iso(row["last_pos"]),
        "birthday": _iso(row["birthday"]), "status": row["status"], "color": row["color"],
        "status_label": STATUS_LABELS.get(row["status"], row["status"]),
    }


def _filters(source) -> dict:
    return {key: (source.get(key) or "").strip() for key in FILTER_KEYS}


def _selected(data) -> set[int]:
    ids = data.get("ids")
    if not isinstance(ids, list) or not ids:
        raise invalid("Aucun adhérent sélectionné.")
    try:
        return {int(i) for i in ids}
    except (TypeError, ValueError):
        raise invalid("Sélection invalide.") from None


@bp.route("/members")
def members_list():
    filters = _filters(request.args)
    rows = member_rows(filters)
    export = {fmt: url_for("entities.members_export", format=fmt, **{k: v for k, v in filters.items() if v})
              for fmt in ("csv", "xlsx")}
    return jsonify(items=[member_payload(r) for r in rows],
                   meta={"export_urls": export, "integrations": integrations_state()})


@bp.route("/members/benevole", methods=["POST"])
def members_set_benevole():
    """`{"ids": [...], "value": bool}` : marque ou retire le statut bénévole."""
    data = json_body()
    ids, value = _selected(data), bool(data.get("value"))
    updated = (Entity.query.filter(Entity.id.in_(ids))
               .update({Entity.is_benevole: value}, synchronize_session=False))
    db.session.commit()
    message = (f"{updated} adhérent(s) marqué(s) bénévole(s)." if value
               else f"{updated} adhérent(s) retiré(s) des bénévoles.")
    return jsonify(updated=updated, notices=[notice(message)])


@bp.route("/members/odoo-notes", methods=["POST"])
def members_update_odoo_notes():
    """`{"ids": [...], filtres}` : écrit la note d'adhésion des fiches Odoo choisies."""
    data = json_body()
    if not odoo_partner_update.is_configured():
        raise ApiError("conflict", external_config.unavailable_message("odoo"), status=409)
    ids = _selected(data)
    chosen = [r for r in member_rows(_filters(data)) if r["entity"] is not None and r["entity"].id in ids]
    if not chosen:
        raise invalid("Aucun adhérent sélectionné.")
    try:
        result = odoo_partner_update.update_member_notes(chosen)
    except OdooConfigError as e:
        raise ApiError("conflict", str(e), status=409) from None
    except Exception as e:  # noqa: BLE001
        current_app.logger.exception("Mise à jour notes Odoo échouée")
        raise ApiError("bad_gateway", f"Erreur Odoo : {e}", status=502) from None
    message = (f"Odoo : {result['updated']} fiche(s) mise(s) à jour, "
               f"{result['skipped']} ignorée(s), {result['errors']} erreur(s).")
    if result["errors"] or result["skipped"]:
        detail = " Détail : " + " | ".join(result["error_lines"][:5]) if result["error_lines"] else ""
        level = "warning" if result["updated"] else "danger"
        return jsonify(result=result, notices=[notice(message + detail, level)])
    return jsonify(result=result, notices=[notice(message)])


@bp.route("/members/reminders")
def members_reminders():
    """Adhérents à relancer (adhésion expirée, email connu) selon les filtres."""
    targets = membership_reminders.members_to_remind(member_rows(_filters(request.args)))
    return jsonify(items=[member_payload(t) for t in targets],
                   meta={"helloasso_url": membership_reminders.helloasso_renewal_url(),
                         "integrations": integrations_state()})


@bp.route("/members/reminders", methods=["POST"])
def members_send_reminders():
    """`{"ids": [...], filtres}` : envoie la relance aux adhérents choisis."""
    data = json_body()
    if not membership_reminders.smtp_configured():
        raise ApiError("conflict", external_config.unavailable_message("smtp"), status=409)
    ids = _selected(data)
    targets = membership_reminders.members_to_remind(member_rows(_filters(data)))
    chosen = [t for t in targets if t["entity"] is not None and t["entity"].id in ids]
    if not chosen:
        raise invalid("Aucun adhérent sélectionné.")
    try:
        result = membership_reminders.send_reminders(chosen)
    except Exception as e:  # noqa: BLE001
        current_app.logger.exception("Relance adhérents échouée")
        raise ApiError("bad_gateway", f"Erreur lors de l'envoi : {e}", status=502) from None
    message = f"Relance : {result['sent']} email(s) envoyé(s), {result['errors']} erreur(s)."
    if result["errors"]:
        return jsonify(result=result, notices=[notice(
            message + " Détail : " + " | ".join(result["error_lines"][:5]),
            "warning" if result["sent"] else "danger")])
    return jsonify(result=result, notices=[notice(message)])


def _sample_row():
    """(row, réelle ?) : un adhérent à relancer pour l'aperçu, sinon un exemple fictif."""
    targets = membership_reminders.members_to_remind(member_rows({}))
    if targets:
        return targets[0], True
    return {"name": "Jean Dupont", "email": "jean.dupont@example.org",
            "birthday": date.today() - timedelta(days=10), "status": "ok", "color": "red",
            "entity": None}, False


def _preview(subject, body_html):
    row, real = _sample_row()
    url = membership_reminders.helloasso_renewal_url()
    try:
        subject_out, body_out = membership_reminders.render_reminder(
            EmailTemplate(key=MEMBERSHIP_REMINDER_KEY, subject=subject, body_html=body_html), row, url)
        error = None
    except Exception as exc:  # noqa: BLE001 — erreur de syntaxe du gabarit, affichée
        subject_out = body_out = ""
        error = str(exc)
    return {"subject": subject_out, "body_html": body_out, "error": error,
            "sample": {"name": row["name"], "email": row["email"], "real": real}}


@bp.route("/members/reminder-template")
def reminder_template_get():
    tpl = EmailTemplate.query.filter_by(key=MEMBERSHIP_REMINDER_KEY).first()
    subject = tpl.subject if tpl else DEFAULT_REMINDER_SUBJECT
    body = tpl.body_html if tpl else DEFAULT_REMINDER_BODY
    return jsonify(item={"subject": subject, "body_html": body}, preview=_preview(subject, body),
                   meta={"helloasso_url": membership_reminders.helloasso_renewal_url()})


@bp.route("/members/reminder-template/preview", methods=["POST"])
def reminder_template_preview():
    data = json_body()
    return jsonify(preview=_preview(str(data.get("subject") or ""), str(data.get("body_html") or "")))


@bp.route("/members/reminder-template", methods=["PUT"])
def reminder_template_save():
    data = json_body()
    subject = str(data.get("subject") or "").strip()
    body = str(data.get("body_html") or "")
    if not subject:
        raise invalid("Le sujet est obligatoire.", "subject")
    if not body.strip():
        raise invalid("Le corps du message est obligatoire.", "body_html")
    tpl = EmailTemplate.query.filter_by(key=MEMBERSHIP_REMINDER_KEY).first()
    if tpl is None:
        tpl = EmailTemplate(key=MEMBERSHIP_REMINDER_KEY)
        db.session.add(tpl)
    tpl.subject, tpl.body_html = subject, body
    db.session.commit()
    return jsonify(item={"subject": subject, "body_html": body},
                   notices=[notice("Gabarit d'email mis à jour.")])
