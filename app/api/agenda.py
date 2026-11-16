"""Échéancier de l'exploitation (lot AG9a) : profil des démarches et base d'échéances.
Lecture pour tous ; profil modifiable par l'administrateur de l'instance. Réservé au plan agricole."""
from datetime import date

from flask import jsonify, request

from app.access import instance_admin_required
from app.services import agri_profile, deadlines

from . import ApiError, bp, json_body, notice


def _agri():
    from app.tenant import current_chart

    if current_chart() != "agri":
        raise ApiError("not_found", "Échéancier réservé aux exploitations agricoles.", 404)


@bp.route("/agri-profile")
def agri_profile_get():
    _agri()
    profile = agri_profile.get()
    return jsonify(item=profile, meta=agri_profile.meta(), hints=agri_profile.hints(profile), uses=agri_profile.uses())


@bp.route("/agri-profile", methods=["PUT"])
@instance_admin_required
def agri_profile_update():
    _agri()
    try:
        profile = agri_profile.save(json_body())
    except agri_profile.ProfileError as exc:
        raise ApiError("validation_error", exc.message, 422, {exc.field: exc.message} if exc.field else None) from None
    return jsonify(item=profile, meta=agri_profile.meta(), hints=agri_profile.hints(profile), uses=agri_profile.uses(),
                   notices=[notice("Activités et démarches enregistrées.")])


@bp.route("/deadlines")
def deadlines_list():
    """Fiches de la base d'échéances, avec leur applicabilité à ce jour (oui, non, à préciser)."""
    _agri()
    ctx = deadlines.context()
    today = date.today()
    items = []
    for fiche in deadlines.fiches():
        applicable = deadlines.applies(fiche.get("applies"), ctx, today)
        items.append({**fiche, "domain_label": deadlines.DOMAINS[fiche["domain"]],
                      "applicable": {True: "yes", False: "no", None: "unknown"}[applicable]})
    return jsonify(items=items, domains=[{"value": k, "label": v} for k, v in deadlines.DOMAINS.items()])


# ------------------------------------------------------------------ échéancier (lot AG9a.b)

def _iso(value):
    return value.isoformat() if value else None


def _day(value, field, default=None):
    if value in (None, ""):
        return default
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise ApiError("validation_error", "Date attendue (AAAA-MM-JJ).", 422, {field: "Date invalide."}) from None


@bp.route("/agenda")
def agenda_list():
    """Occurrences de `?from=` à `?to=` (défaut : J-90 à J+400), fiches utilisées, questions à régler, détections.
    Rattache d'abord les paiements reconnus sur les relevés (lot AG9a.c)."""
    from app.extensions import db
    from app.services import agenda, agenda_checks

    _agri()
    today = date.today()
    default_from, default_to = agenda.window(today)
    start, end = _day(request.args.get("from"), "from", default_from), _day(request.args.get("to"), "to", default_to)
    if end < start or (end - start).days > 800:
        raise ApiError("validation_error", "Période invalide (26 mois au plus).", 422, {"to": "Période invalide."})
    ctx = deadlines.context()
    if agenda.match_payments(today, ctx):
        db.session.commit()
    data = agenda.occurrences(start, end, today, ctx)
    if (start, end) == (default_from, default_to):
        checks = agenda_checks.detections(today, ctx, data["items"])
    else:
        checks = agenda_checks.detections(today, ctx, agenda.occurrences(default_from, default_to, today, ctx)["items"])
    used = {i["fiche_id"] for i in data["items"]} | set(data["questions"])
    items = [{**i, "date": _iso(i["date"]), "edi_date": _iso(i["edi_date"]), "reminder_from": _iso(i["reminder_from"])}
             for i in data["items"]]
    return jsonify(items=items, questions=data["questions"], detections=checks, today=_iso(today), start=_iso(start), end=_iso(end),
                   fiches={f["id"]: agenda.fiche_payload(f) for f in deadlines.fiches() if f["id"] in used},
                   statuses=[{"value": k, "label": v} for k, v in agenda.STATUSES.items()],
                   domains=[{"value": k, "label": v} for k, v in deadlines.DOMAINS.items()])


@bp.route("/agenda/states", methods=["POST"])
def agenda_state_create():
    from flask_login import current_user

    from app.extensions import db
    from app.services import agenda

    _agri()
    data = json_body()
    occurs_on = _day(data.get("occurs_on"), "occurs_on")
    if occurs_on is None:
        raise ApiError("validation_error", "Date de l'échéance obligatoire.", 422, {"occurs_on": "Obligatoire."})
    try:
        tx_id = data.get("bank_transaction_id")
        if tx_id is not None and not isinstance(tx_id, int):
            raise agenda.AgendaError("Identifiant de transaction attendu.", "bank_transaction_id")
        state = agenda.set_state(str(data.get("deadline_id") or ""), occurs_on, str(data.get("period") or ""),
                                 str(data.get("status") or ""), _day(data.get("done_on"), "done_on"), data.get("note"),
                                 current_user.id, bank_transaction_id=tx_id)
        db.session.commit()
    except agenda.AgendaError as exc:
        db.session.rollback()
        raise ApiError("conflict" if exc.status == 409 else "not_found" if exc.status == 404 else "validation_error",
                       exc.message, exc.status, {exc.field: exc.message} if exc.field else None) from None
    label = "Paiement rattaché" if state.origin == "bank" else \
        f"Échéance marquée {'faite' if state.status == 'done' else 'ignorée'}"
    return jsonify(item=agenda.state_payload(state), notices=[notice(f"{label}.")]), 201


@bp.route("/agenda/states/<int:state_id>", methods=["DELETE"])
def agenda_state_delete(state_id):
    from app.extensions import db
    from app.models import DeadlineState
    from app.services import agenda

    from . import get_or_404

    _agri()
    state = get_or_404(DeadlineState, state_id, "État introuvable.")
    if state.status == "unlinked":
        raise ApiError("not_found", "État introuvable.", 404)
    bank = state.origin == "bank"
    agenda.clear_state(state)
    db.session.commit()
    return jsonify(notices=[notice("Paiement détaché : l'échéance est à nouveau à faire." if bank
                                   else "Échéance remise à faire.")])


@bp.route("/agenda/candidates")
def agenda_candidates():
    """Débits de l'organisme autour d'une échéance de paiement (`?deadline_id=&occurs_on=&period=`), pour la
    rattacher à la main."""
    from app.services import agenda

    _agri()
    occurs_on = _day(request.args.get("occurs_on"), "occurs_on")
    if occurs_on is None:
        raise ApiError("validation_error", "Date de l'échéance obligatoire.", 422, {"occurs_on": "Obligatoire."})
    deadline_id, period = request.args.get("deadline_id") or "", request.args.get("period") or ""
    try:
        item = agenda.find_occurrence(deadline_id, occurs_on, period, date.today())
    except agenda.AgendaError as exc:
        raise ApiError("not_found", exc.message, 404) from None
    return jsonify(items=agenda.candidates(item) if item["payment"] else [])


# ------------------------------------------------------------------ résumé du lundi (lot AG9a.d)

@bp.route("/agenda/summary")
def agenda_summary_get():
    """Résumé de la semaine (tableau de bord) ; rattache les paiements reconnus comme l'échéancier."""
    from app.extensions import db
    from app.services import agenda_summary

    _agri()
    summary = agenda_summary.weekly_summary(date.today())
    db.session.commit()
    return jsonify(item=summary)


def _subscription_payload():
    from flask_login import current_user

    from app.access import current_role
    from app.models.instance_membership import ROLE_ACCOUNTANT
    from app.services import agenda_summary
    from app.tenant import current_instance

    row = agenda_summary.subscription_of(current_user.id)
    return {"subscribed": agenda_summary.is_subscribed(current_user, current_instance()), "email": current_user.email,
            "available": current_role() != ROLE_ACCOUNTANT,
            "last_sent_week": row.last_sent_week if row else None}


@bp.route("/agenda/subscription")
def agenda_subscription_get():
    _agri()
    return jsonify(item=_subscription_payload())


@bp.route("/agenda/subscription", methods=["PUT"])
def agenda_subscription_update():
    from flask_login import current_user

    from app.extensions import db
    from app.services import agenda_summary

    _agri()
    value = json_body().get("subscribed")
    if not isinstance(value, bool):
        raise ApiError("validation_error", "Oui ou non attendu.", 422, {"subscribed": "Oui ou non attendu."})
    agenda_summary.set_subscribed(current_user.id, value)
    db.session.commit()
    message = "Vous recevrez le résumé du lundi par e-mail." if value else "Vous ne recevrez plus le résumé du lundi."
    return jsonify(item=_subscription_payload(), notices=[notice(message)])


# ------------------------------------------------------------------ export iCal (lot AG9a.e)

def _ical_payload():
    from flask_login import current_user

    from app.services import agenda_ical, password_reset
    from app.tenant import current_instance

    token = agenda_ical.token_of(current_user.id)
    base = password_reset.base_url() or ""
    url = f"{base}/agenda/ical/{current_instance().slug}/{token}.ics" if token else None
    return {"url": url}


@bp.route("/agenda/ical")
def agenda_ical_get():
    _agri()
    return jsonify(item=_ical_payload())


@bp.route("/agenda/ical", methods=["POST"])
def agenda_ical_create():
    """Crée ou régénère l'URL secrète du calendrier : l'ancienne cesse de marcher."""
    from flask_login import current_user

    from app.extensions import db
    from app.services import agenda_ical

    _agri()
    renewed = agenda_ical.token_of(current_user.id) is not None
    agenda_ical.regenerate(current_user.id)
    db.session.commit()
    message = "Nouvelle adresse du calendrier : l'ancienne ne fonctionne plus." if renewed else "Adresse du calendrier créée."
    return jsonify(item=_ical_payload(), notices=[notice(message)])


@bp.route("/agenda/ical", methods=["DELETE"])
def agenda_ical_delete():
    from flask_login import current_user

    from app.extensions import db
    from app.services import agenda_ical

    _agri()
    agenda_ical.revoke(current_user.id)
    db.session.commit()
    return jsonify(item=_ical_payload(), notices=[notice("Adresse du calendrier révoquée.")])
