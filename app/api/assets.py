"""Immobilisations (lot F5) : registre, fiches, tableau d'amortissement, mise en service, sortie,
dotations de l'exercice (assistant de clôture), tableau de l'annexe."""
from datetime import date

from flask import jsonify, request
from flask_login import current_user

from app.extensions import db
from app.models import Account, Asset, FiscalYear, PurchaseLine
from app.services import assets
from app.services.ledger_errors import LedgerError

from app.models.asset import LIVING_KINDS, LIVING_ORIGINS

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
            "enabled": assets.enabled(),
            "living_kinds": [{"value": k, "label": v} for k, v in LIVING_KINDS.items()],
            "plantation_references": assets.plantation_references(),
            "living_origins": [{"value": k, "label": v} for k, v in LIVING_ORIGINS.items()]}


@bp.route("/assets")
def assets_list():
    query = Asset.query.filter(Asset.parent_id.is_(None)).order_by(Asset.acquired_on.desc(), Asset.id.desc())
    status = request.args.get("status")
    items = [assets.payload(a) for a in query]
    if request.args.get("living") == "1":                      # lot AG5.a : biens vivants seulement
        items = [i for i in items if i["living"]]
    if status:
        items = [i for i in items if i["status"] == status]
    return jsonify(items=items, meta=_meta())


@bp.route("/assets/ledger-gaps")
def assets_ledger_gaps():
    """Immobilisations comptabilisées sans fiche : écart entre le grand livre et le registre, par compte."""
    fy_id = request.args.get("fy_id", type=int)
    fy = (db.session.get(FiscalYear, fy_id) if fy_id else None) or (
        FiscalYear.query.filter(FiscalYear.start_date <= date.today()).order_by(FiscalYear.start_date.desc()).first()
        or FiscalYear.query.order_by(FiscalYear.start_date.desc()).first())
    if fy is None:
        return jsonify(items=[], fiscal_year=None)
    return jsonify(items=assets.ledger_gaps(fy), fiscal_year={"id": fy.id, "label": fy.label, "end_date": fy.end_date.isoformat()})


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
        current = assets.payload(asset)
        living = current.get("living") or {}
        assets.save(asset, {**current, "account_id": asset.account_id, "living_kind": living.get("kind"),
                            "species": living.get("species"), "age_class": living.get("age_class"),
                            "units": asset.units, "origin": living.get("origin"), **json_body()})
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


@bp.route("/assets/<int:asset_id>/living-exit", methods=["POST"])
def assets_living_exit(asset_id):
    """Sortie d'un bien vivant (lot AG5.a) : `{date, kind: sold|scrapped, units?, price_cents?, sale_id?}` ; `units`
    inférieur à l'effectif : sortie partielle au coût moyen (AGD22)."""
    asset = get_or_404(Asset, asset_id, "Immobilisation introuvable.")
    data = json_body()
    price = data.get("price_cents") or 0
    if not isinstance(price, int) or isinstance(price, bool) or price < 0:
        raise invalid("Prix invalide.", "price_cents")
    try:
        target, entry = assets.living_exit(asset, _date(data, "date"), data.get("units"), data.get("kind"), price,
                                           data.get("sale_id") if isinstance(data.get("sale_id"), int) else None,
                                           current_user.id)
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    db.session.expire_all()
    return jsonify(item=assets.payload(asset, with_schedule=True), exited=assets.payload(target),
                   notices=[notice(f"Sortie enregistrée ({entry.reference}).")])


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


# ------------------------------------------------------------------ biens vivants en cours, entrée depuis le stock (AG5.b)

def _wip_view(fy):
    from app.services import living_assets

    entry = living_assets.wip_entry(fy)
    return {"items": living_assets.wip_rows(fy), "enabled": assets.enabled(),
            "entry": {"id": entry.id, "reference": entry.reference} if entry else None}


@bp.route("/fiscal-years/<int:fy_id>/closing/living-wip")
def living_wip(fy_id):
    from app.models import FiscalYear
    return jsonify(**_wip_view(get_or_404(FiscalYear, fy_id, "Exercice introuvable.")))


@bp.route("/fiscal-years/<int:fy_id>/closing/living-wip/costs", methods=["PUT"])
def living_wip_cost(fy_id):
    from app.models import FiscalYear
    from app.services import living_assets

    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    data = json_body()
    try:
        living_assets.set_wip_cost(fy, data.get("asset_id"), data.get("amount_cents"), data.get("basis"))
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    return jsonify(**_wip_view(fy), notices=[notice("Coût de croissance enregistré.")])


@bp.route("/fiscal-years/<int:fy_id>/closing/living-wip", methods=["POST"])
def living_wip_post(fy_id):
    from app.models import FiscalYear
    from app.services import living_assets

    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    try:
        entry = living_assets.post_wip(fy)
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    message = f"En-cours passés ({entry.reference})." if entry else "Aucun coût à porter en en-cours."
    return jsonify(**_wip_view(fy), notices=[notice(message)])


@bp.route("/fiscal-years/<int:fy_id>/closing/living-wip", methods=["DELETE"])
def living_wip_cancel(fy_id):
    from app.models import FiscalYear
    from app.services import living_assets

    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    try:
        living_assets.cancel_wip(fy)
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    return jsonify(**_wip_view(fy), notices=[notice("Écriture des en-cours annulée.")])


@bp.route("/stock-lots/<int:lot_id>/to-fixed-assets", methods=["POST"])
def stock_lot_to_fixed_assets(lot_id):
    """Animal du stock devenu reproducteur : mouvement du lot + fiche immobilisée (D 24x / C 724)."""
    from app.models import StockLot
    from app.services import living_assets
    from app.services.stock_inventory import StockError

    lot = get_or_404(StockLot, lot_id, "Lot introuvable.")
    try:
        movement = living_assets.from_stock(lot, json_body(), current_user.id)
    except StockError as exc:
        db.session.rollback()
        raise ApiError("validation_error" if exc.status == 422 else "conflict", exc.message, exc.status,
                       {exc.field: exc.message} if exc.field else None) from None
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    return jsonify(item=assets.payload(movement.asset), notices=[notice(f"Fiche « {movement.asset.label} » créée, "
                                                                       "entrée en production en 724.")]), 201


# ------------------------------------------------------------------ sorties, réinvestissements, dépréciations (AG5.c)

@bp.route("/assets/<int:asset_id>/living-exits", methods=["POST"])
def assets_living_exits(asset_id):
    """Sortie typée d'un bien vivant : `{date, kind: sale|death|casualty|sanitary_slaughter|scrap, units?, price_cents?,
    indemnity_cents?, sale_id?, note?}`."""
    from app.services import living_exits

    asset = get_or_404(Asset, asset_id, "Immobilisation introuvable.")
    try:
        row = living_exits.exit_living(asset, json_body(), current_user.id)
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    db.session.expire_all()
    return jsonify(item=assets.payload(asset, with_schedule=True), exit=living_exits.exit_payload(row),
                   notices=[notice("Sortie enregistrée.")])


@bp.route("/living-exits")
def living_exits_list():
    from app.models import AssetLivingExit
    from app.services import living_exits

    rows = AssetLivingExit.query.order_by(AssetLivingExit.on.desc(), AssetLivingExit.id.desc()).all()
    return jsonify(items=[living_exits.exit_payload(r) for r in rows])


@bp.route("/living-reinvestments/<int:reinvestment_id>", methods=["PUT"])
def living_reinvestment_update(reinvestment_id):
    from app.models import LivingReinvestment
    from app.services import living_exits

    row = get_or_404(LivingReinvestment, reinvestment_id, "Réinvestissement introuvable.")
    try:
        living_exits.update_reinvestment(row, json_body())
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    return jsonify(item=living_exits.reinvestment_payload(row), notices=[notice("Réinvestissement enregistré.")])


def _impairment_view(fy):
    from app.services import living_exits

    entry = living_exits.impairment_entry(fy)
    return {"items": living_exits.impairment_rows(fy), "enabled": assets.enabled(),
            "entry": {"id": entry.id, "reference": entry.reference} if entry else None}


@bp.route("/fiscal-years/<int:fy_id>/closing/living-impairments")
def living_impairments(fy_id):
    return jsonify(**_impairment_view(get_or_404(FiscalYear, fy_id, "Exercice introuvable.")))


@bp.route("/fiscal-years/<int:fy_id>/closing/living-impairments/values", methods=["PUT"])
def living_impairment_set(fy_id):
    from app.services import living_exits

    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    data = json_body()
    try:
        living_exits.set_impairment(fy, data.get("asset_id"), data.get("amount_cents"), data.get("reason"))
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    return jsonify(**_impairment_view(fy), notices=[notice("Dépréciation enregistrée.")])


@bp.route("/fiscal-years/<int:fy_id>/closing/living-impairments", methods=["POST"])
def living_impairments_post(fy_id):
    from app.services import living_exits

    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    try:
        entry = living_exits.post_impairments(fy)
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    return jsonify(**_impairment_view(fy), notices=[notice(f"Dépréciations passées ({entry.reference})." if entry
                                                           else "Aucune dépréciation à passer.")])


@bp.route("/fiscal-years/<int:fy_id>/closing/living-impairments", methods=["DELETE"])
def living_impairments_cancel(fy_id):
    from app.services import living_exits

    fy = get_or_404(FiscalYear, fy_id, "Exercice introuvable.")
    try:
        living_exits.cancel_impairments(fy)
    except LedgerError as exc:
        raise _error(exc) from None
    db.session.commit()
    return jsonify(**_impairment_view(fy), notices=[notice("Écriture des dépréciations annulée.")])
