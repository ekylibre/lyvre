"""Aides PAC et subventions (lot AG3.a, claudedocs/design_aides_pac.md § 8.3) : dispositifs, dossiers, versements
saisis à la main, nouvelle campagne PAC. Réservé aux exploitations agricoles (plan `agri`), en partie double comme en
comptabilité simplifiée (micro-BA : suivi seulement)."""
from contextlib import contextmanager

from flask import jsonify, request

from app.extensions import db
from app.models import Aid, AidPayment
from app.models.aid import AID_NATURES, AID_PAYMENT_KINDS, AID_STATUSES, AID_TRIGGERS
from app.services import aids
from app.services.aids import AidError

from . import ApiError, bp, get_or_404, json_body, notice


def _agri():
    from app.tenant import current_chart

    if current_chart() != "agri":
        raise ApiError("not_found", "Registre des aides réservé aux exploitations agricoles.", 404)


@contextmanager
def _errors():
    try:
        yield
    except AidError as exc:
        db.session.rollback()
        code = {409: "conflict", 404: "not_found"}.get(exc.status, "validation_error")
        raise ApiError(code, exc.message, exc.status, {exc.field: exc.message} if exc.field else None) from None


def _options(mapping):
    return [{"value": k, "label": v} for k, v in mapping.items()]


def _meta():
    return {"natures": _options(AID_NATURES), "triggers": _options(AID_TRIGGERS), "statuses": _options(AID_STATUSES),
            "payment_kinds": _options(AID_PAYMENT_KINDS), "campaigns": aids.campaigns(),
            "default_campaign": aids.default_campaign()}


@bp.route("/aids/schemes")
def aid_schemes():
    _agri()
    return jsonify(items=[aids.scheme_payload(s) for s in aids.schemes()])


@bp.route("/aids")
def aid_list():
    _agri()
    raw = request.args.get("campaign")
    campaign = aids.default_campaign() if raw == "default" else request.args.get("campaign", type=int)
    status = request.args.get("status") or None
    if status and status not in AID_STATUSES:
        raise ApiError("validation_error", "Statut inconnu.", 422)
    rows = aids.listing(campaign, status)
    return jsonify(items=[aids.payload(a, with_payments=False) for a in rows], totals=aids.totals(rows), meta=_meta(),
                   ledger=aids.ledger_lines(campaign) if campaign else [], campaign=campaign)


@bp.route("/aids/from-ledger", methods=["POST"])
def aid_from_ledger():
    """Dossier créé depuis des écritures d'aides déjà comptabilisées (reprise d'historique) : versements rattachés."""
    _agri()
    with _errors():
        aid = aids.create_from_ledger(json_body())
        db.session.commit()
    count = len(aid.payments)
    return jsonify(item=aids.payload(aid), notices=[notice(
        f"Dossier « {aid.label} » {aid.campaign} créé avec {count} versement{'s' if count > 1 else ''} rattaché"
        f"{'s' if count > 1 else ''}.")]), 201


@bp.route("/aids/<int:aid_id>/ledger-lines", methods=["POST"])
def aid_link_ledger(aid_id):
    _agri()
    aid = get_or_404(Aid, aid_id)
    with _errors():
        body = json_body()
        payments = aids.link_lines(aid, body.get("line_ids"), body.get("amounts"))
        db.session.commit()
    count = len(payments)
    return jsonify(item=aids.payload(aid), notices=[notice(
        f"{count} écriture{'s' if count > 1 else ''} rattachée{'s' if count > 1 else ''} à « {aid.label} ».")])


@bp.route("/aids", methods=["POST"])
def aid_create():
    _agri()
    with _errors():
        aid = aids.create(json_body())
        db.session.commit()
    return jsonify(item=aids.payload(aid), notices=[notice(f"Dossier « {aid.label} » {aid.campaign} créé.")]), 201


@bp.route("/aids/<int:aid_id>")
def aid_detail(aid_id):
    _agri()
    return jsonify(item=aids.payload(get_or_404(Aid, aid_id, "Dossier introuvable.")))


@bp.route("/aids/<int:aid_id>", methods=["PUT"])
def aid_update(aid_id):
    _agri()
    aid = get_or_404(Aid, aid_id, "Dossier introuvable.")
    with _errors():
        aids.update(aid, json_body())
        db.session.commit()
    return jsonify(item=aids.payload(aid), notices=[notice("Dossier enregistré.")])


@bp.route("/aids/<int:aid_id>", methods=["DELETE"])
def aid_delete(aid_id):
    _agri()
    aid = get_or_404(Aid, aid_id, "Dossier introuvable.")
    with _errors():
        aids.delete(aid)
        db.session.commit()
    return jsonify(notices=[notice("Dossier supprimé.")])


@bp.route("/aids/<int:aid_id>/payments", methods=["POST"])
def aid_payment_add(aid_id):
    _agri()
    aid = get_or_404(Aid, aid_id, "Dossier introuvable.")
    with _errors():
        aids.add_payment(aid, json_body())
        db.session.commit()
    return jsonify(item=aids.payload(aid), notices=[notice("Versement enregistré.")]), 201


@bp.route("/aids/<int:aid_id>/payments/<int:payment_id>", methods=["DELETE"])
def aid_payment_delete(aid_id, payment_id):
    _agri()
    payment = get_or_404(AidPayment, payment_id, "Versement introuvable.")
    if payment.aid_id != aid_id:
        raise ApiError("not_found", "Versement introuvable.", 404)
    aid, from_bank = payment.aid, payment.bank_transaction_id is not None
    with _errors():
        aids.delete_payment(payment)
        db.session.commit()
    message = ("Virement détaché du dossier ; son écriture est conservée." if from_bank else "Versement supprimé.")
    return jsonify(item=aids.payload(aid), notices=[notice(message)])


@bp.route("/aids/pac-campaign")
def aid_pac_proposals():
    _agri()
    campaign = request.args.get("campaign", type=int)
    if campaign is None:
        raise ApiError("validation_error", "Campagne : année attendue.", 422, {"campaign": "Année attendue."})
    return jsonify(items=aids.pac_proposals(campaign))


@bp.route("/aids/pac-campaign", methods=["POST"])
def aid_pac_create():
    _agri()
    data = json_body()
    with _errors():
        created = aids.create_pac_campaign(data.get("campaign"), data.get("schemes"))
        db.session.commit()
    count = len(created)
    message = f"{count} dossier{'s' if count > 1 else ''} créé{'s' if count > 1 else ''} pour la campagne {data.get('campaign')}." \
        if count else "Tous ces dossiers existent déjà."
    return jsonify(items=[aids.payload(a, with_payments=False) for a in created], notices=[notice(message)]), 201


# ------------------------------------------------------------------ virements (lot AG3.b)

@bp.route("/aids/candidates")
def aid_candidates():
    _agri()
    from app.services import aid_payments

    with _errors():
        data = aid_payments.candidates(request.args.get("bank_transaction_id", type=int))
    return jsonify(item=data)


@bp.route("/aids/link", methods=["POST"])
def aid_link():
    _agri()
    from app.services import aid_payments

    data = json_body()
    book = data.get("book", False)
    if not isinstance(book, bool):
        raise ApiError("validation_error", "book : vrai ou faux attendu.", 422)
    with _errors():
        result = aid_payments.link(data.get("bank_transaction_id"), data.get("allocations"), book=book)
        db.session.commit()
    count = len(data["allocations"])
    message = (f"Virement rattaché à {count} dossier{'s' if count > 1 else ''}"
               + (" et comptabilisé." if result["booked"] else "."))
    return jsonify(item=result, notices=[notice(message), *(notice(w, "warning") for w in result["warnings"])])


# ------------------------------------------------------------------ clôture (lot AG3.c)

def _fy(fy_id):
    from app.models import FiscalYear

    return get_or_404(FiscalYear, fy_id, "Exercice introuvable.")


def _open(fy):
    if fy.status != "open":
        raise ApiError("conflict", "Exercice clôturé : rouvrez-le pour modifier l'inventaire.", 409)


@bp.route("/fiscal-years/<int:fy_id>/closing/aids")
def aid_accruals(fy_id):
    from app.services import aid_closing

    return jsonify(**aid_closing.proposals(_fy(fy_id)), enabled=aid_closing.enabled())


@bp.route("/fiscal-years/<int:fy_id>/closing/aids", methods=["POST"])
def aid_accruals_post(fy_id):
    """`{items: [{key, amount_cents?, reason?}]}` : écritures d'inventaire des aides retenues."""
    from flask_login import current_user

    from app.services import aid_closing
    from app.services.closing import ClosingError

    _agri()
    fy = _fy(fy_id)
    _open(fy)
    with _errors():
        try:
            entries = aid_closing.post(fy, json_body().get("items"), current_user.id)
        except ClosingError as exc:
            raise AidError(exc.message, "items", exc.status) from None
    return jsonify(**aid_closing.proposals(fy), notices=[notice(f"{len(entries)} écriture(s) d'inventaire passée(s).")])


@bp.route("/fiscal-years/<int:fy_id>/closing/aids/dismissed", methods=["POST"])
def aid_accruals_dismiss(fy_id):
    from flask_login import current_user

    from app.services import aid_closing

    _agri()
    fy = _fy(fy_id)
    _open(fy)
    data = json_body()
    with _errors():
        aid_closing.dismiss(fy, data.get("aid_id"), data.get("reason"), current_user.id)
        db.session.commit()
    return jsonify(**aid_closing.proposals(fy), notices=[notice("Proposition écartée.")])


@bp.route("/fiscal-years/<int:fy_id>/closing/aids/dismissed/<int:aid_id>", methods=["DELETE"])
def aid_accruals_restore(fy_id, aid_id):
    from app.services import aid_closing

    _agri()
    fy = _fy(fy_id)
    _open(fy)
    with _errors():
        aid_closing.restore(fy, aid_id)
        db.session.commit()
    return jsonify(**aid_closing.proposals(fy), notices=[notice("Proposition rétablie.")])


# ------------------------------------------------------------------ subventions d'investissement (lot AG3.d)

@bp.route("/aids/<int:aid_id>/grant", methods=["POST"])
def aid_grant(aid_id):
    from app.services import aid_grants

    _agri()
    aid = get_or_404(Aid, aid_id, "Dossier introuvable.")
    with _errors():
        entry = aid_grants.grant(aid)
        db.session.commit()
    return jsonify(item=aids.payload(aid), notices=[notice(f"Octroi passé ({entry.reference}) : D 441 / C {aid.account.code}.")])


@bp.route("/aids/<int:aid_id>/grant", methods=["DELETE"])
def aid_grant_cancel(aid_id):
    from app.services import aid_grants

    _agri()
    aid = get_or_404(Aid, aid_id, "Dossier introuvable.")
    with _errors():
        aid_grants.cancel_grant(aid)
        db.session.commit()
    return jsonify(item=aids.payload(aid), notices=[notice("Octroi annulé.")])


@bp.route("/aids/<int:aid_id>/assets", methods=["PUT"])
def aid_assets(aid_id):
    from app.services import aid_grants

    _agri()
    aid = get_or_404(Aid, aid_id, "Dossier introuvable.")
    with _errors():
        aid_grants.set_assets(aid, json_body().get("assets"))
        db.session.commit()
    return jsonify(item=aids.payload(aid), notices=[notice("Immobilisations financées enregistrées.")])


def _grants_payload(fy):
    from app.services import aid_grants

    entry = aid_grants.release_entry(fy)
    return {"items": aid_grants.releases(fy), "annex": aid_grants.annex(fy), "enabled": aid_grants.enabled(),
            "entry": {"id": entry.id, "reference": entry.reference} if entry else None}


@bp.route("/fiscal-years/<int:fy_id>/closing/aid-releases")
def aid_releases(fy_id):
    return jsonify(**_grants_payload(_fy(fy_id)))


@bp.route("/fiscal-years/<int:fy_id>/closing/aid-releases", methods=["POST"])
def aid_releases_post(fy_id):
    from app.services import aid_grants

    _agri()
    fy = _fy(fy_id)
    with _errors():
        entry = aid_grants.post_releases(fy)
        db.session.commit()
    message = f"Reprise passée ({entry.reference})." if entry else "Aucune reprise à passer."
    return jsonify(**_grants_payload(fy), notices=[notice(message)])


@bp.route("/fiscal-years/<int:fy_id>/closing/aid-releases", methods=["DELETE"])
def aid_releases_cancel(fy_id):
    from app.services import aid_grants

    _agri()
    fy = _fy(fy_id)
    with _errors():
        aid_grants.cancel_releases(fy)
        db.session.commit()
    return jsonify(**_grants_payload(fy), notices=[notice("Écriture de reprise annulée.")])


@bp.route("/fiscal-years/<int:fy_id>/closing/aid-releases/manual", methods=["POST"])
def aid_releases_manual(fy_id):
    from app.services import aid_grants

    _agri()
    fy = _fy(fy_id)
    data = json_body()
    with _errors():
        aid_grants.add_manual(fy, data.get("aid_id"), data.get("amount_cents"), data.get("reason"), data.get("asset_id"))
        db.session.commit()
    return jsonify(**_grants_payload(fy), notices=[notice("Reprise saisie ; elle sera passée avec l'écriture de reprise.")])


@bp.route("/fiscal-years/<int:fy_id>/closing/aid-releases/manual/<int:release_id>", methods=["DELETE"])
def aid_releases_manual_delete(fy_id, release_id):
    from app.services import aid_grants

    _agri()
    fy = _fy(fy_id)
    with _errors():
        aid_grants.delete_manual(fy, release_id)
        db.session.commit()
    return jsonify(**_grants_payload(fy), notices=[notice("Reprise saisie supprimée.")])


# ------------------------------------------------------------------ montants publiés par l'ASP (lot AG3.e)

@bp.route("/aids/cap-check")
def aid_cap_check():
    from app.services import aid_cap

    _agri()
    year = request.args.get("year", type=int)
    with _errors():
        data = aid_cap.check(year, force=False)
    return jsonify(item=data)


@bp.route("/aids/cap-check", methods=["POST"])
def aid_cap_refresh():
    """Relit Lexicon (cache de l'instance remplacé) : action d'écriture, refusée à l'expert-comptable."""
    from app.services import aid_cap

    _agri()
    year = json_body().get("year")
    with _errors():
        data = aid_cap.check(year, force=True)
    level = "warning" if data["message"] and not data["published"] else "success"
    return jsonify(item=data, notices=[notice(data["message"] or "Montants publiés relus dans Lexicon.", level)])
