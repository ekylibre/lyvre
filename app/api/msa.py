"""Cotisations MSA des non-salariés agricoles (lot AG7, claudedocs/design_msa.md) : assiette sociale par exploitant."""
from contextlib import contextmanager

from flask import jsonify

from app.extensions import db
from app.models import FiscalYear
from app.services import msa
from app.services.msa import MsaError

from . import ApiError, bp, get_or_404, json_body, notice


def _fy(fy_id):
    if not msa.enabled():
        raise ApiError("not_found", "MSA réservée aux exploitations au réel (partie double).", 404)
    return get_or_404(FiscalYear, fy_id, "Exercice introuvable.")


@contextmanager
def _errors():
    try:
        yield
    except MsaError as exc:
        db.session.rollback()
        code = {409: "conflict", 404: "not_found"}.get(exc.status, "validation_error")
        raise ApiError(code, exc.message, exc.status, {exc.field: exc.message} if exc.field else None) from None


@bp.route("/fiscal-years/<int:fy_id>/msa")
def msa_view(fy_id):
    return jsonify(item=msa.view(_fy(fy_id)), meta=msa.meta())


@bp.route("/fiscal-years/<int:fy_id>/msa/adjustments", methods=["POST"])
def msa_adjustment_add(fy_id):
    fy = _fy(fy_id)
    with _errors():
        msa.add_adjustment(fy, json_body())
        db.session.commit()
    return jsonify(item=msa.view(fy), meta=msa.meta(), notices=[notice("Ligne ajoutée.")]), 201


@bp.route("/fiscal-years/<int:fy_id>/msa/adjustments/<int:adj_id>", methods=["DELETE"])
def msa_adjustment_delete(fy_id, adj_id):
    fy = _fy(fy_id)
    with _errors():
        msa.delete_adjustment(fy, adj_id)
        db.session.commit()
    return jsonify(item=msa.view(fy), meta=msa.meta(), notices=[notice("Ligne supprimée.")])


@bp.route("/msa/people/<int:person_id>", methods=["PATCH"])
def msa_person_update(person_id):
    if not msa.enabled():
        raise ApiError("not_found", "MSA réservée aux exploitations au réel (partie double).", 404)
    with _errors():
        person = msa.update_person(person_id, json_body())
        db.session.commit()
    return jsonify(item=msa.person_payload(person), notices=[notice("Exploitant mis à jour.")])


@bp.route("/msa/people/<int:person_id>/bases/<int:year>", methods=["PUT"])
def msa_base_save(person_id, year):
    if not msa.enabled():
        raise ApiError("not_found", "MSA réservée aux exploitations au réel (partie double).", 404)
    with _errors():
        row = msa.save_base(person_id, year, json_body())
        db.session.commit()
    return jsonify(item=msa.base_payload(row), notices=[notice("Assiette enregistrée.")])


@bp.route("/msa/people/<int:person_id>/bases/<int:year>", methods=["DELETE"])
def msa_base_delete(person_id, year):
    if not msa.enabled():
        raise ApiError("not_found", "MSA réservée aux exploitations au réel (partie double).", 404)
    with _errors():
        msa.delete_base(person_id, year)
        db.session.commit()
    return jsonify(notices=[notice("Assiette supprimée.")])


# ------------------------------------------------------------------ appels de cotisations (lot AG7.c)

def _require():
    if not msa.enabled():
        raise ApiError("not_found", "MSA réservée aux exploitations au réel (partie double).", 404)


def _year():
    from datetime import date

    from flask import request
    raw = request.args.get("year")
    try:
        return int(raw) if raw else date.today().year
    except ValueError:
        raise ApiError("validation_error", "Année attendue.", 422) from None


@bp.route("/msa/calls")
def msa_calls_list():
    from app.services import msa_calls
    _require()
    return jsonify(item=msa_calls.listing(_year()))


@bp.route("/msa/calls", methods=["POST"])
def msa_call_create():
    from app.services import msa_calls
    _require()
    with _errors():
        call = msa_calls.create(json_body())
        db.session.commit()
    return jsonify(item=msa_calls.listing(call.year), notices=[notice("Appel enregistré.")]), 201


@bp.route("/msa/calls/monthly", methods=["POST"])
def msa_calls_monthly():
    from app.services import msa_calls
    _require()
    body = json_body()
    with _errors():
        calls = msa_calls.monthly(body.get("person_id"), body.get("year"), body.get("day"))
        db.session.commit()
    return jsonify(item=msa_calls.listing(calls[0].year), notices=[notice("Mensualités proposées : à corriger d'après l'échéancier de la caisse.")]), 201


@bp.route("/msa/calls/<int:call_id>", methods=["PATCH"])
def msa_call_update(call_id):
    from app.services import msa_calls
    _require()
    with _errors():
        call = msa_calls.update(call_id, json_body())
        db.session.commit()
    return jsonify(item=msa_calls.listing(call.year), notices=[notice("Appel mis à jour.")])


@bp.route("/msa/calls/<int:call_id>", methods=["DELETE"])
def msa_call_delete(call_id):
    from app.services import msa_calls
    _require()
    with _errors():
        msa_calls.delete(call_id)
        db.session.commit()
    return jsonify(notices=[notice("Appel supprimé.")])


@bp.route("/msa/calls/<int:call_id>/estimate", methods=["POST"])
def msa_call_estimate(call_id):
    from app.services import msa_calls
    _require()
    with _errors():
        call = msa_calls.apply_proposal(call_id)
        db.session.commit()
    return jsonify(item=msa_calls.listing(call.year), notices=[notice("Détail estimé appliqué.")])


@bp.route("/msa/calls/<int:call_id>/candidates")
def msa_call_candidates(call_id):
    from app.services import msa_calls
    _require()
    with _errors():
        items = msa_calls.candidates(call_id)
    return jsonify(items=items)


@bp.route("/msa/calls/<int:call_id>/payment", methods=["PUT"])
def msa_call_payment(call_id):
    from app.services import msa_calls
    _require()
    with _errors():
        call = msa_calls.link_payment(call_id, json_body().get("bank_transaction_id"))
        db.session.commit()
    return jsonify(item=msa_calls.listing(call.year), notices=[notice("Paiement rattaché." if call.bank_transaction_id else "Paiement détaché.")])


# ------------------------------------------------------------------ ventilation (lot AG7.d)

@bp.route("/fiscal-years/<int:fy_id>/msa/ventilation")
def msa_ventilation_view(fy_id):
    from app.services import msa_ventilation
    return jsonify(item=msa_ventilation.view(_fy(fy_id)))


@bp.route("/fiscal-years/<int:fy_id>/msa/accrual", methods=["POST"])
def msa_accrual_post(fy_id):
    from flask_login import current_user

    from app.services import msa_ventilation
    fy = _fy(fy_id)
    with _errors():
        entry = msa_ventilation.post_accrual(fy, getattr(current_user, "id", None))
    return jsonify(item=msa_ventilation.view(fy), notices=[notice(f"Charge à payer passée ({entry.reference}).")]), 201


@bp.route("/fiscal-years/<int:fy_id>/msa/accrual", methods=["DELETE"])
def msa_accrual_delete(fy_id):
    from flask_login import current_user

    from app.services import msa_ventilation
    fy = _fy(fy_id)
    with _errors():
        msa_ventilation.delete_accrual(fy, getattr(current_user, "id", None))
        db.session.commit()
    return jsonify(item=msa_ventilation.view(fy), notices=[notice("Charge à payer supprimée.")])
