"""Immobilisations (lot F5) : registre, fiches, tableau d'amortissement, mise en service, sortie,
dotations de l'exercice (assistant de clôture), tableau de l'annexe."""
from datetime import date

from flask import jsonify, request
from flask_login import current_user

from app.extensions import db
from app.models import Account, Asset, FiscalYear, PurchaseLine
from app.services import assets
from app.services.ledger_errors import LedgerError

from . import ApiError, bp, get_or_404, invalid, json_body, notice


def _error(exc):
    db.session.rollback()
    if isinstance(exc, assets.AssetError) and exc.field:
        return ApiError("validation_error", str(exc), exc.status, {exc.field: str(exc)})
    return ApiError(getattr(exc, "code", "conflict"), str(exc), 409)


def _date(data, key):
    try:
        return date.fromisoformat(str(data.get(key) or ""))
    except ValueError:
        raise invalid("Date invalide.", key) from None


def _meta():
    accounts = Account.query.filter(Account.code.like("2%"), Account.is_header.is_(False),
                                    ~Account.code.like("28%"), ~Account.code.like("29%")).order_by(Account.code)
    return {"accounts": [{"value": str(a.id), "label": f"{a.code} — {a.label}"} for a in accounts],
            "methods": [{"value": k, "label": v} for k, v in assets.METHOD_LABELS.items()],
            "statuses": [{"value": k, "label": v} for k, v in assets.STATUS_LABELS.items()],
            "enabled": assets.enabled()}


@bp.route("/assets")
def assets_list():
    query = Asset.query.filter(Asset.parent_id.is_(None)).order_by(Asset.acquired_on.desc(), Asset.id.desc())
    status = request.args.get("status")
    items = [assets.payload(a) for a in query]
    if status:
        items = [i for i in items if i["status"] == status]
    return jsonify(items=items, meta=_meta())


@bp.route("/assets", methods=["POST"])
def assets_create():
    try:
        asset = assets.save(None, json_body())
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    return jsonify(item=assets.payload(asset), notices=[notice(f"Immobilisation « {asset.label} » créée.")]), 201


@bp.route("/assets/<int:asset_id>")
def assets_get(asset_id):
    return jsonify(item=assets.payload(get_or_404(Asset, asset_id, "Immobilisation introuvable."), with_schedule=True),
                   meta=_meta())


@bp.route("/assets/<int:asset_id>", methods=["PATCH"])
def assets_update(asset_id):
    asset = get_or_404(Asset, asset_id, "Immobilisation introuvable.")
    if asset.status in ("sold", "scrapped"):
        raise ApiError("conflict", "Immobilisation sortie : la fiche ne se modifie plus.", 409)
    try:
        assets.save(asset, {**assets.payload(asset), "account_id": asset.account_id, **json_body()})
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    return jsonify(item=assets.payload(asset, with_schedule=True), notices=[notice("Immobilisation enregistrée.")])


@bp.route("/assets/<int:asset_id>", methods=["DELETE"])
def assets_delete(asset_id):
    asset = get_or_404(Asset, asset_id, "Immobilisation introuvable.")
    if not assets.payload(asset)["deletable"]:
        raise ApiError("conflict", "Dotations ou écritures passées : la fiche ne se supprime plus (sortez-la de l'actif).", 409)
    db.session.delete(asset)
    db.session.commit()
    return jsonify(notices=[notice("Immobilisation supprimée.")])


@bp.route("/assets/<int:asset_id>/in-service", methods=["POST"])
def assets_in_service(asset_id):
    asset = get_or_404(Asset, asset_id, "Immobilisation introuvable.")
    data = json_body()
    try:
        entry = assets.put_in_service(asset, _date(data, "date"), data.get("account_id"), current_user.id)
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    return jsonify(item=assets.payload(asset, with_schedule=True),
                   notices=[notice(f"Mise en service enregistrée ({entry.reference}).")])


@bp.route("/assets/<int:asset_id>/dispose", methods=["POST"])
def assets_dispose(asset_id):
    """`{date, kind: sold|scrapped, price_cents?, sale_id?}`."""
    asset = get_or_404(Asset, asset_id, "Immobilisation introuvable.")
    data = json_body()
    price = data.get("price_cents") or 0
    if not isinstance(price, int) or isinstance(price, bool) or price < 0:
        raise invalid("Prix invalide.", "price_cents")
    try:
        entry = assets.dispose(asset, _date(data, "date"), data.get("kind"), price,
                               data.get("sale_id") if isinstance(data.get("sale_id"), int) else None, current_user.id)
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    return jsonify(item=assets.payload(asset, with_schedule=True), notices=[notice(f"Sortie enregistrée ({entry.reference}).")])


@bp.route("/purchases/<int:purchase_id>/lines/<int:line_id>/asset", methods=["POST"])
def purchase_line_asset(purchase_id, line_id):
    """Fiche préremplie depuis une ligne de facture d'achat (compte 2x)."""
    line = get_or_404(PurchaseLine, line_id, "Ligne introuvable.")
    if line.purchase_id != purchase_id:
        raise ApiError("not_found", "Ligne introuvable.", 404)
    try:
        asset = assets.from_purchase_line(line)
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    return jsonify(item=assets.payload(asset), notices=[notice(f"Immobilisation « {asset.label} » créée : vérifiez sa durée.")]), 201


@bp.route("/fiscal-years/<int:fy_id>/closing/depreciation")
def fiscal_year_depreciation(fy_id):
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    entry = assets.depreciation_entry(fy)
    return jsonify(items=assets.depreciation_rows(fy), enabled=assets.enabled(),
                   entry={"id": entry.id, "reference": entry.reference} if entry else None)


@bp.route("/fiscal-years/<int:fy_id>/closing/depreciation", methods=["POST"])
def fiscal_year_depreciation_post(fy_id):
    """Passe (ou repasse) les dotations de l'exercice."""
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    try:
        entry = assets.post_depreciation(fy, current_user.id)
    except LedgerError as exc:
        raise _error(exc) from None
    message = f"Dotations passées ({entry.reference})." if entry else "Aucune dotation pour l'exercice."
    return jsonify(items=assets.depreciation_rows(fy), notices=[notice(message)])


@bp.route("/fiscal-years/<int:fy_id>/closing/depreciation", methods=["DELETE"])
def fiscal_year_depreciation_cancel(fy_id):
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    try:
        assets.cancel_depreciation(fy)
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    return jsonify(items=assets.depreciation_rows(fy), notices=[notice("Dotations de l'exercice retirées.")])


@bp.route("/fiscal-years/<int:fy_id>/assets/annex")
def fiscal_year_assets_annex(fy_id):
    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    return jsonify(items=assets.annex(fy))
