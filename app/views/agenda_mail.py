"""Liens publics de l'échéancier, sans connexion : désabonnement du résumé du lundi (lot AG9a.d) et calendrier
iCal (lot AG9a.e).

Désabonnement :

Le jeton signé désigne l'utilisateur et l'instance ; la page demande une confirmation (POST) pour qu'une
prévisualisation automatique du lien par la messagerie ne désabonne pas. Route hors instance
(`app/tenant.py`) : la base de l'instance est choisie d'après le jeton.
"""
from flask import Blueprint, g, render_template, request

from app.extensions import csrf, db
from app.models import Instance

bp = Blueprint("agenda_mail", __name__)


@bp.route("/agenda/unsubscribe", methods=["GET", "POST"])
@csrf.exempt   # le jeton signé tient lieu de preuve
def unsubscribe():
    from app.services import agenda_summary

    token = request.values.get("token", "")
    parsed = agenda_summary.read_unsubscribe_token(token)
    instance = db.session.get(Instance, parsed[0]) if parsed else None
    if instance is None or not instance.is_active:
        return render_template("agenda/unsubscribe.html", state="invalid"), 404
    if request.method == "GET":
        return render_template("agenda/unsubscribe.html", state="confirm", token=token, label=instance.label)
    previous = (getattr(g, "current_instance", None), getattr(g, "tenant_engine", None))
    try:
        agenda_summary._select(instance)
        agenda_summary.set_subscribed(parsed[1], False)
        db.session.commit()
    finally:
        g.current_instance, g.tenant_engine = previous
    return render_template("agenda/unsubscribe.html", state="done", label=instance.label)


@bp.route("/agenda/ical/<slug>/<token>.ics")
def ical(slug, token):
    """Calendrier iCal de l'échéancier (lot AG9a.e) : URL secrète par utilisateur et par instance, sans connexion.
    Réponse identique (404) pour une instance inconnue, un jeton faux ou révoqué, un accès retiré."""
    from flask import Response, abort

    from app.access import role_for
    from app.models import User
    from app.services import agenda_ical, agenda_summary, organization, password_reset

    instance = Instance.query.filter_by(slug=slug).first()
    if instance is None or not instance.is_active or instance.chart != "agri":
        abort(404)
    previous = (getattr(g, "current_instance", None), getattr(g, "tenant_engine", None))
    try:
        agenda_summary._select(instance)
        user_id = agenda_ical.owner_of(token)
        user = db.session.get(User, user_id) if user_id is not None else None
        if user is None or not user.is_active or role_for(user, instance) is None:
            abort(404)
        base_url = password_reset.base_url() or ""
        body = agenda_ical.calendar(organization.get().name or instance.label, instance.slug, base_url)
    finally:
        g.current_instance, g.tenant_engine = previous
    response = Response(body, mimetype="text/calendar")
    response.headers["Content-Type"] = "text/calendar; charset=utf-8"
    response.headers["Content-Disposition"] = f'inline; filename="echeancier-{instance.slug}.ics"'
    response.headers["Cache-Control"] = "private, max-age=3600"
    response.headers["X-Robots-Tag"] = "noindex"
    return response
