"""Plan comptable (écran Compta › Plan comptable). `/accounts` reste la recherche des
combobox (lookups.py) ; la gestion du plan est sous `/chart-of-accounts`."""
from flask import jsonify

from app.extensions import db
from app.models import Account
from app.models.account import ACCOUNT_TYPES

from . import bp, get_or_404, invalid, json_body, notice

TYPE_CODES = {code for code, _ in ACCOUNT_TYPES}


def account_payload(a: Account) -> dict:
    return {"id": a.id, "code": a.code, "label": a.label, "account_type": a.account_type,
            "is_header": a.is_header, "parent_code": a.parent.code if a.parent else None}


def _label_and_type(data):
    label = str(data.get("label") or "").strip()
    if not label:
        raise invalid("Le libellé est obligatoire.", "label")
    account_type = data.get("account_type") or "OTHER"
    if account_type not in TYPE_CODES:
        raise invalid("Type de compte inconnu.", "account_type")
    return label[:255], account_type


@bp.route("/chart-of-accounts")
def chart_list():
    accounts = Account.query.order_by(Account.code).all()
    return jsonify(items=[account_payload(a) for a in accounts],
                   meta={"types": [{"value": c, "label": l} for c, l in ACCOUNT_TYPES]})


@bp.route("/chart-of-accounts", methods=["POST"])
def chart_create():
    data = json_body()
    code = str(data.get("code") or "").strip()
    if not code:
        raise invalid("Le code est obligatoire.", "code")
    if len(code) > 20:
        raise invalid("Le code fait 20 caractères au plus.", "code")
    if Account.query.filter_by(code=code).first():
        raise invalid(f"Le compte {code} existe déjà.", "code")
    label, account_type = _label_and_type(data)
    parent_code = str(data.get("parent_code") or "").strip()
    parent = None
    if parent_code:
        parent = Account.query.filter_by(code=parent_code).first()
        if parent is None:
            raise invalid(f"Compte parent « {parent_code} » introuvable.", "parent_code")
    account = Account(code=code, label=label, account_type=account_type, parent=parent)
    db.session.add(account)
    db.session.commit()
    return jsonify(item=account_payload(account), notices=[notice(f"Compte {code} créé.")]), 201


@bp.route("/chart-of-accounts/<int:account_id>", methods=["PATCH"])
def chart_update(account_id):
    """Libellé et type ; le code d'un compte ne change pas (écritures, règles, produits)."""
    account = get_or_404(Account, account_id, "Compte introuvable.")
    account.label, account.account_type = _label_and_type(json_body())
    db.session.commit()
    return jsonify(item=account_payload(account), notices=[notice(f"Compte {account.code} mis à jour.")])
