"""Relance par email des adhérents dont l'adhésion est expirée (statut rouge).

Le service reçoit les ``rows`` déjà construites par la vue
(``membership_status.build_member_rows``) pour éviter toute dépendance circulaire
avec le blueprint ``entities``.

La configuration SMTP est **par instance** : elle est lue depuis la table
``external_connections`` (service ``smtp``) via ``external_config``, avec repli
sur les variables d'environnement ``MAIL_*``. L'envoi se fait en ``smtplib`` pour
ne pas dépendre d'une config Flask-Mail globale (incompatible multi-tenant).
"""
import smtplib
from email.message import EmailMessage

from flask import render_template_string

from app.extensions import db
from app.models import HelloAssoOrder, HelloAssoItem
from app.models.email_template import EmailTemplate, MEMBERSHIP_REMINDER_KEY
from app.services import external_config


def _truthy(value):
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def smtp_settings():
    """Retourne la configuration SMTP de l'instance (DB puis repli .env)."""
    raw_port = external_config.get("smtp", "port")
    try:
        port = int(raw_port) if raw_port else 587
    except (TypeError, ValueError):
        port = 587
    raw_tls = external_config.get("smtp", "use_tls")
    return {
        "host": external_config.get("smtp", "host") or "",
        "port": port,
        "use_tls": True if raw_tls is None else _truthy(raw_tls),
        "username": external_config.get("smtp", "username") or "",
        "password": external_config.get("smtp", "password") or "",
        "sender": external_config.get("smtp", "sender") or "",
    }


def smtp_configured():
    """Vrai si le serveur SMTP minimal (host + expéditeur) est paramétré."""
    return external_config.is_configured("smtp")


def _open_smtp(settings, timeout=20):
    """Ouvre une connexion SMTP authentifiée selon la configuration."""
    server = smtplib.SMTP(settings["host"], settings["port"], timeout=timeout)
    if settings["use_tls"]:
        server.starttls()
    if settings["username"]:
        server.login(settings["username"], settings["password"])
    return server


def check_smtp_connection():
    """Teste la connexion SMTP. Retourne (ok: bool, message: str)."""
    if not smtp_configured():
        return False, "SMTP non configuré (host et expéditeur requis)."
    settings = smtp_settings()
    try:
        server = _open_smtp(settings)
        try:
            server.noop()
        finally:
            server.quit()
    except Exception as exc:  # noqa: BLE001 — message remonté à l'UI
        return False, f"Échec de connexion : {exc}"
    return True, (
        f"Connexion SMTP réussie ({settings['host']}:{settings['port']}, "
        f"TLS {'activé' if settings['use_tls'] else 'désactivé'})."
    )


def _build_message(sender, recipient, subject, html):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(
        "Cet email nécessite un client compatible HTML pour être affiché."
    )
    msg.add_alternative(html, subtype="html")
    return msg


def members_to_remind(rows):
    """Filtre les rows : adhésion expirée (rouge), email présent, statut connu.

    Les adhérents sans aucune donnée d'adhésion (``status == "?"``) sont exclus :
    rien à renouveler et email souvent absent.
    """
    return [
        r for r in rows
        if r["color"] == "red" and r.get("email") and r["status"] != "?"
    ]


def _most_common_membership_form():
    """Slug du formulaire HelloAsso le plus fréquent parmi les adhésions connues."""
    row = (
        db.session.query(HelloAssoOrder.form_slug, db.func.count())
        .join(HelloAssoItem, HelloAssoItem.order_id == HelloAssoOrder.id)
        .filter(HelloAssoItem.type == "Membership")
        .filter(HelloAssoOrder.form_slug.isnot(None))
        .group_by(HelloAssoOrder.form_slug)
        .order_by(db.func.count().desc())
        .first()
    )
    return (row[0] if row else None) or "adhesion"


def helloasso_renewal_url():
    """Construit le lien public de renouvellement d'adhésion HelloAsso."""
    slug = external_config.get("helloasso", "org_slug") or ""
    form_slug = _most_common_membership_form()
    if not slug:
        return ""
    return f"https://www.helloasso.com/associations/{slug}/adhesions/{form_slug}"


def render_reminder(template, row, helloasso_url):
    """Rend (sujet, corps HTML) du gabarit pour un adhérent donné."""
    context = {
        "nom": row["name"],
        "email": row.get("email") or "",
        "date_anniversaire": row["birthday"].strftime("%d/%m/%Y"),
        "lien_helloasso": helloasso_url,
    }
    subject = render_template_string(template.subject, **context)
    body = render_template_string(template.body_html, **context)
    return subject, body


def send_reminders(rows, dry_run=False):
    """Envoie un email de relance à chaque row éligible.

    Retourne ``{"sent", "skipped", "errors", "error_lines"}``. Une erreur sur un
    adhérent n'interrompt pas le lot.
    """
    targets = members_to_remind(rows)
    template = EmailTemplate.get_or_default(MEMBERSHIP_REMINDER_KEY)
    helloasso_url = helloasso_renewal_url()

    sent = skipped = errors = 0
    error_lines = []

    if dry_run:
        return {
            "sent": 0, "skipped": 0, "errors": 0,
            "error_lines": [], "targets": targets,
        }

    if not smtp_configured():
        return {
            "sent": 0, "skipped": len(targets), "errors": 0,
            "error_lines": ["SMTP non configuré."], "targets": targets,
        }

    settings = smtp_settings()
    sender = settings["sender"]
    server = _open_smtp(settings)
    try:
        for row in targets:
            try:
                subject, body = render_reminder(template, row, helloasso_url)
                msg = _build_message(sender, row["email"], subject, body)
                server.send_message(msg)
                sent += 1
            except Exception as exc:  # noqa: BLE001 — on isole l'échec par adhérent
                errors += 1
                error_lines.append(f"{row['name']} <{row['email']}> — {exc}")
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001 — fermeture best-effort
            pass

    return {
        "sent": sent,
        "skipped": skipped,
        "errors": errors,
        "error_lines": error_lines,
        "targets": targets,
    }
