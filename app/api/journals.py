"""Journaux comptables (écran Compta › Journaux)."""
from flask import jsonify

from app.extensions import db
from app.models import Journal

from . import bp, invalid, json_body, notice


def journal_payload(j: Journal) -> dict:
    return {"id": j.id, "code": j.code, "label": j.label}


@bp.route("/journals")
def journals_list():
    journals = Journal.query.order_by(Journal.code).all()
    return jsonify(items=[journal_payload(j) for j in journals])


@bp.route("/journals", methods=["POST"])
def journals_create():
    data = json_body()
    code = str(data.get("code") or "").strip().upper()
    label = str(data.get("label") or "").strip()
    if not code:
        raise invalid("Le code est obligatoire.", "code")
    if len(code) > 10:
        raise invalid("Le code fait 10 caractères au plus.", "code")
    if not label:
        raise invalid("Le libellé est obligatoire.", "label")
    if Journal.query.filter_by(code=code).first():
        raise invalid(f"Le journal {code} existe déjà.", "code")
    journal = Journal(code=code, label=label[:100])
    db.session.add(journal)
    db.session.commit()
    return jsonify(item=journal_payload(journal), notices=[notice(f"Journal {code} créé.")]), 201
