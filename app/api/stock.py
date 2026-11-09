"""Inventaire de clôture des exploitations (lot AG4.a, claudedocs/design_inventaire_agricole.md § 9.3) : lignes de
stock, réglages (décotes, date du comptage), reprise de l'exercice précédent, import d'un tableur, feuilles de
comptage, barèmes de coût standard. Plan agricole en partie double ; 404 au micro-BA (AG4.7)."""
from contextlib import contextmanager

from flask import abort, jsonify, request, send_file

from app.extensions import db
from app.models import FiscalYear, StockCountFile, StockLine, StockStandard
from app.services import stock_inventory as inv
from app.services.stock_inventory import StockError

from . import ApiError, bp, get_or_404, json_body, notice


def _fy(fy_id):
    if not inv.enabled():
        raise ApiError("not_found", "Inventaire de clôture réservé aux exploitations au réel (partie double).", 404)
    return get_or_404(FiscalYear, fy_id, "Exercice introuvable.")


@contextmanager
def _errors():
    try:
        yield
    except StockError as exc:
        db.session.rollback()
        code = {409: "conflict", 404: "not_found"}.get(exc.status, "validation_error")
        raise ApiError(code, exc.message, exc.status, {exc.field: exc.message} if exc.field else None) from None


def _view(fy):
    from app.services import stock_entry

    return {"item": inv.overview(fy), "meta": inv.meta(), "entry": stock_entry.status(fy),
            "files": [_file(f) for f in StockCountFile.query.filter_by(fiscal_year_id=fy.id)]}


def _file(row):
    return {"id": row.id, "name": row.attachment_name, "mime": row.attachment_mime, "size": row.attachment_size,
            "note": row.note, "created_at": row.created_at.isoformat(timespec="seconds")}


@bp.route("/fiscal-years/<int:fy_id>/stock")
def stock_view(fy_id):
    return jsonify(**_view(_fy(fy_id)))


@bp.route("/fiscal-years/<int:fy_id>/stock/lines", methods=["POST"])
def stock_line_create(fy_id):
    fy = _fy(fy_id)
    with _errors():
        inv.create_line(fy, json_body())
        db.session.commit()
    return jsonify(**_view(fy), notices=[notice("Ligne ajoutée.")]), 201


@bp.route("/fiscal-years/<int:fy_id>/stock/lines/<int:line_id>", methods=["PUT"])
def stock_line_update(fy_id, line_id):
    fy = _fy(fy_id)
    line = get_or_404(StockLine, line_id, "Ligne introuvable.")
    with _errors():
        inv.update_line(fy, line, json_body())
        db.session.commit()
    return jsonify(**_view(fy), notices=[notice("Ligne enregistrée.")])


@bp.route("/fiscal-years/<int:fy_id>/stock/lines/<int:line_id>", methods=["DELETE"])
def stock_line_delete(fy_id, line_id):
    fy = _fy(fy_id)
    line = get_or_404(StockLine, line_id, "Ligne introuvable.")
    with _errors():
        inv.delete_line(fy, line)
        db.session.commit()
    return jsonify(**_view(fy), notices=[notice("Ligne supprimée.")])


@bp.route("/fiscal-years/<int:fy_id>/stock/settings", methods=["PUT"])
def stock_settings(fy_id):
    fy = _fy(fy_id)
    with _errors():
        inv.set_settings(fy, json_body())
        db.session.commit()
    return jsonify(**_view(fy), notices=[notice("Réglages de l'inventaire enregistrés.")])


@bp.route("/fiscal-years/<int:fy_id>/stock/copy-previous", methods=["POST"])
def stock_copy_previous(fy_id):
    fy = _fy(fy_id)
    with _errors():
        count = inv.copy_previous(fy)
        db.session.commit()
    return jsonify(**_view(fy), notices=[notice(f"{count} ligne(s) reprise(s) de l'exercice précédent, quantités à zéro.")])


@bp.route("/fiscal-years/<int:fy_id>/stock/copy-opening", methods=["POST"])
def stock_copy_opening(fy_id):
    """Premier inventaire : une ligne par compte de stock ouvert, quantité et valeur à saisir."""
    fy = _fy(fy_id)
    with _errors():
        count = inv.copy_opening(fy)
        db.session.commit()
    return jsonify(**_view(fy), notices=[notice(f"{count} ligne(s) créée(s) depuis les stocks initiaux : comptez et "
                                                "valorisez chacune avant de passer l'écriture.")])


@bp.route("/fiscal-years/<int:fy_id>/stock/import", methods=["POST"])
def stock_import(fy_id):
    fy = _fy(fy_id)
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise ApiError("validation_error", "Fichier CSV ou XLSX attendu.", 422, {"file": "Fichier attendu."})
    content = upload.stream.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise ApiError("validation_error", "Fichier trop volumineux (5 Mo au plus).", 422)
    with _errors():
        count = inv.import_lines(fy, upload.filename, content)
        db.session.commit()
    return jsonify(**_view(fy), notices=[notice(f"{count} ligne(s) importée(s).")]), 201


# ------------------------------------------------------------------ feuilles de comptage

@bp.route("/fiscal-years/<int:fy_id>/stock/files", methods=["POST"])
def stock_file_upload(fy_id):
    from app.services import attachments

    fy = _fy(fy_id)
    if fy.status != "open":
        raise ApiError("conflict", "Exercice clôturé : l'inventaire est figé.", 409)
    upload = request.files.get("file")
    row = StockCountFile(fiscal_year_id=fy.id, note=(request.form.get("note") or "").strip()[:300] or None)
    db.session.add(row)
    db.session.flush()
    try:
        attachments.store(row, attachments.stage(upload), folder="inventaire", day=fy.end_date)
    except attachments.AttachmentError as exc:
        db.session.rollback()
        raise ApiError("validation_error", str(exc), 422, {"file": str(exc)}) from None
    db.session.commit()
    return jsonify(**_view(fy), notices=[notice("Feuille de comptage jointe.")]), 201


@bp.route("/fiscal-years/<int:fy_id>/stock/files/<int:file_id>")
def stock_file_download(fy_id, file_id):
    from app.services import attachments

    fy = _fy(fy_id)
    row = get_or_404(StockCountFile, file_id, "Pièce introuvable.")
    path = attachments.path_of(row) if row.fiscal_year_id == fy.id else None
    if path is None:
        abort(404)
    return send_file(path, mimetype=row.attachment_mime, download_name=row.attachment_name or path.name,
                     as_attachment=bool(request.args.get("download")))


@bp.route("/fiscal-years/<int:fy_id>/stock/files/<int:file_id>", methods=["DELETE"])
def stock_file_delete(fy_id, file_id):
    from app.services import attachments

    fy = _fy(fy_id)
    row = get_or_404(StockCountFile, file_id, "Pièce introuvable.")
    if row.fiscal_year_id != fy.id:
        raise ApiError("not_found", "Pièce introuvable.", 404)
    if fy.status != "open":
        raise ApiError("conflict", "Exercice clôturé : l'inventaire est figé.", 409)
    path = attachments.path_of(row)
    if path is not None:
        path.unlink(missing_ok=True)
    db.session.delete(row)
    db.session.commit()
    return jsonify(**_view(fy), notices=[notice("Pièce supprimée.")])


# ------------------------------------------------------------------ barèmes de coût standard

def _standards_guard():
    if not inv.enabled():
        raise ApiError("not_found", "Barèmes réservés aux exploitations au réel (partie double).", 404)


@bp.route("/stock-standards")
def stock_standards():
    _standards_guard()
    return jsonify(items=inv.meta()["standards"])


@bp.route("/stock-standards", methods=["POST"])
def stock_standard_create():
    _standards_guard()
    with _errors():
        row = inv.save_standard(None, json_body())
        db.session.commit()
    return jsonify(item=inv.standard_payload(row), notices=[notice("Barème enregistré.")]), 201


@bp.route("/stock-standards/<int:standard_id>", methods=["PUT"])
def stock_standard_update(standard_id):
    _standards_guard()
    row = get_or_404(StockStandard, standard_id, "Barème introuvable.")
    with _errors():
        inv.save_standard(row, json_body())
        db.session.commit()
    return jsonify(item=inv.standard_payload(row), notices=[notice("Barème enregistré.")])


@bp.route("/stock-standards/<int:standard_id>", methods=["DELETE"])
def stock_standard_delete(standard_id):
    _standards_guard()
    row = get_or_404(StockStandard, standard_id, "Barème introuvable.")
    with _errors():
        inv.delete_standard(row)
        db.session.commit()
    return jsonify(notices=[notice("Barème supprimé.")])


# ------------------------------------------------------------------ lots d'animaux (lot AG4.b)

def _lot_fy():
    fy_id = request.args.get("fiscal_year_id", type=int)
    return get_or_404(FiscalYear, fy_id, "Exercice introuvable.") if fy_id else None


def _lot_response(lot, fy, status=200, message=None):
    from app.services import stock_lots

    body = {"item": stock_lots.lot_payload(lot, fy, with_movements=fy is not None)}
    if message:
        body["notices"] = [notice(message)]
    return jsonify(**body), status


@bp.route("/stock-lots")
def stock_lots_list():
    from app.services import stock_lots

    _standards_guard()
    fy = _lot_fy()
    from app.models import StockLot
    return jsonify(items=[stock_lots.lot_payload(lot, fy) for lot in StockLot.query.order_by(StockLot.label)])


@bp.route("/stock-lots", methods=["POST"])
def stock_lot_create():
    from app.services import stock_lots

    _standards_guard()
    with _errors():
        lot = stock_lots.create_lot(json_body())
        db.session.commit()
    return _lot_response(lot, _lot_fy(), 201, f"Lot « {lot.label} » créé.")


@bp.route("/stock-lots/<int:lot_id>")
def stock_lot_detail(lot_id):
    from app.models import StockLot

    _standards_guard()
    return _lot_response(get_or_404(StockLot, lot_id, "Lot introuvable."), _lot_fy())


@bp.route("/stock-lots/<int:lot_id>", methods=["PUT"])
def stock_lot_update(lot_id):
    from app.models import StockLot
    from app.services import stock_lots

    _standards_guard()
    lot = get_or_404(StockLot, lot_id, "Lot introuvable.")
    with _errors():
        stock_lots.update_lot(lot, json_body())
        db.session.commit()
    return _lot_response(lot, _lot_fy(), message="Lot enregistré.")


@bp.route("/stock-lots/<int:lot_id>", methods=["DELETE"])
def stock_lot_delete(lot_id):
    from app.models import StockLot
    from app.services import stock_lots

    _standards_guard()
    lot = get_or_404(StockLot, lot_id, "Lot introuvable.")
    with _errors():
        stock_lots.delete_lot(lot)
        db.session.commit()
    return jsonify(notices=[notice("Lot supprimé.")])


@bp.route("/stock-lots/<int:lot_id>/movements", methods=["POST"])
def stock_lot_movement_add(lot_id):
    from app.models import StockLot
    from app.services import stock_lots

    _standards_guard()
    lot = get_or_404(StockLot, lot_id, "Lot introuvable.")
    with _errors():
        stock_lots.add_movement(lot, json_body())
        db.session.commit()
    return _lot_response(lot, _lot_fy(), 201, "Mouvement enregistré.")


@bp.route("/stock-lots/<int:lot_id>/movements/<int:movement_id>", methods=["DELETE"])
def stock_lot_movement_delete(lot_id, movement_id):
    from app.models import StockLot, StockLotMovement
    from app.services import stock_lots

    _standards_guard()
    lot = get_or_404(StockLot, lot_id, "Lot introuvable.")
    movement = get_or_404(StockLotMovement, movement_id, "Mouvement introuvable.")
    with _errors():
        stock_lots.delete_movement(lot, movement)
        db.session.commit()
    db.session.expire(lot)
    return _lot_response(lot, _lot_fy(), message="Mouvement supprimé.")


# ------------------------------------------------------------------ avances aux cultures (lot AG4.c)

def _advance(advance_id):
    from app.models import CropAdvance

    _standards_guard()
    return get_or_404(CropAdvance, advance_id, "Fiche introuvable.")


def _advance_response(advance, status=200, message=None):
    from app.services import crop_advances

    body = {"item": crop_advances.payload(advance, with_proposals=True), "meta": crop_advances.meta()}
    if message:
        body["notices"] = [notice(message)]
    return jsonify(**body), status


@bp.route("/fiscal-years/<int:fy_id>/crop-advances", methods=["POST"])
def crop_advance_create(fy_id):
    from app.services import crop_advances

    fy = _fy(fy_id)
    with _errors():
        advance = crop_advances.create(fy, json_body())
        db.session.commit()
    return _advance_response(advance, 201, f"Avance aux cultures « {advance.production} » créée.")


@bp.route("/crop-advances/<int:advance_id>")
def crop_advance_detail(advance_id):
    return _advance_response(_advance(advance_id))


@bp.route("/crop-advances/<int:advance_id>", methods=["PUT"])
def crop_advance_update(advance_id):
    from app.services import crop_advances

    advance = _advance(advance_id)
    with _errors():
        crop_advances.update(advance, json_body())
        db.session.commit()
    return _advance_response(advance, message="Fiche enregistrée.")


@bp.route("/crop-advances/<int:advance_id>", methods=["DELETE"])
def crop_advance_delete(advance_id):
    from app.services import crop_advances

    advance = _advance(advance_id)
    with _errors():
        crop_advances.delete(advance)
        db.session.commit()
    return jsonify(notices=[notice("Fiche et ligne d'inventaire supprimées.")])


@bp.route("/crop-advances/<int:advance_id>/costs", methods=["POST"])
def crop_advance_cost_add(advance_id):
    from app.services import crop_advances

    advance = _advance(advance_id)
    with _errors():
        crop_advances.add_cost(advance, json_body())
        db.session.commit()
    return _advance_response(advance, 201, "Charge rattachée.")


@bp.route("/crop-advances/<int:advance_id>/costs/<int:cost_id>", methods=["DELETE"])
def crop_advance_cost_delete(advance_id, cost_id):
    from app.models import CropAdvanceCost
    from app.services import crop_advances

    advance = _advance(advance_id)
    cost = get_or_404(CropAdvanceCost, cost_id, "Charge introuvable.")
    with _errors():
        crop_advances.delete_cost(advance, cost)
        db.session.commit()
    return _advance_response(advance, message="Charge retirée.")


@bp.route("/crop-standards")
def crop_standards_list():
    from app.services import crop_advances

    _standards_guard()
    return jsonify(items=crop_advances.meta()["standards"])


@bp.route("/crop-standards", methods=["POST"])
def crop_standard_create():
    from app.services import crop_advances

    _standards_guard()
    with _errors():
        row = crop_advances.save_standard(None, json_body())
        db.session.commit()
    return jsonify(item=crop_advances.standard_payload(row), notices=[notice("Barème enregistré.")]), 201


@bp.route("/crop-standards/<int:standard_id>", methods=["PUT"])
def crop_standard_update(standard_id):
    from app.models import CropStandard
    from app.services import crop_advances

    _standards_guard()
    row = get_or_404(CropStandard, standard_id, "Barème introuvable.")
    with _errors():
        crop_advances.save_standard(row, json_body())
        db.session.commit()
    return jsonify(item=crop_advances.standard_payload(row), notices=[notice("Barème enregistré.")])


@bp.route("/crop-standards/<int:standard_id>", methods=["DELETE"])
def crop_standard_delete(standard_id):
    from app.models import CropStandard
    from app.services import crop_advances

    _standards_guard()
    row = get_or_404(CropStandard, standard_id, "Barème introuvable.")
    with _errors():
        crop_advances.delete_standard(row)
        db.session.commit()
    return jsonify(notices=[notice("Barème supprimé.")])


@bp.route("/crop-standards/import", methods=["POST"])
def crop_standards_import():
    from app.services import crop_advances

    _standards_guard()
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise ApiError("validation_error", "Fichier CSV attendu.", 422, {"file": "Fichier attendu."})
    with _errors():
        count, warnings = crop_advances.import_standards(upload.stream.read(2 * 1024 * 1024))
        db.session.commit()
    notices = [notice(f"{count} barème(s) importé(s).")] + [notice(w, "warning") for w in warnings]
    return jsonify(items=crop_advances.meta()["standards"], notices=notices), 201


# ------------------------------------------------------------------ écriture de stock (lot AG4.d)

@bp.route("/fiscal-years/<int:fy_id>/stock/entry", methods=["POST"])
def stock_entry_post(fy_id):
    from flask_login import current_user

    from app.services import stock_entry

    fy = _fy(fy_id)
    with _errors():
        result = stock_entry.post(fy, current_user.id)
        db.session.commit()
    message = f"Écriture de stock passée ({result.reference})." if result else "Aucun stock : pas d'écriture."
    return jsonify(**_view(fy), notices=[notice(message)])


@bp.route("/fiscal-years/<int:fy_id>/stock/entry", methods=["DELETE"])
def stock_entry_cancel(fy_id):
    from app.services import stock_entry

    fy = _fy(fy_id)
    with _errors():
        stock_entry.cancel(fy)
        db.session.commit()
    return jsonify(**_view(fy), notices=[notice("Écriture de stock annulée.")])


# ------------------------------------------------------------------ stock d'entrée au passage au réel (lot CG5.c)

def _opening(fy, status=200, message=None):
    from app.services import opening_stock

    body = {"item": opening_stock.payload(fy)}
    if message:
        body["notices"] = [notice(message)]
    return jsonify(**body), status


@bp.route("/fiscal-years/<int:fy_id>/opening-stock")
def opening_stock_view(fy_id):
    return _opening(_fy(fy_id))


@bp.route("/fiscal-years/<int:fy_id>/opening-stock/lines", methods=["POST"])
def opening_stock_add(fy_id):
    from app.services import opening_stock

    fy = _fy(fy_id)
    with _errors():
        opening_stock.add_line(fy, json_body())
        db.session.commit()
    return _opening(fy, 201, "Ligne ajoutée au stock d'entrée.")


@bp.route("/fiscal-years/<int:fy_id>/opening-stock/lines/<int:line_id>", methods=["PUT", "DELETE"])
def opening_stock_line(fy_id, line_id):
    from app.models import OpeningStockLine
    from app.services import opening_stock

    fy = _fy(fy_id)
    line = get_or_404(OpeningStockLine, line_id, "Ligne introuvable.")
    if line.fiscal_year_id != fy.id:
        raise ApiError("not_found", "Ligne introuvable.", 404)
    with _errors():
        if request.method == "DELETE":
            opening_stock.delete_line(fy, line)
        else:
            opening_stock.update_line(fy, line, json_body())
        db.session.commit()
    return _opening(fy, message="Stock d'entrée enregistré.")


@bp.route("/fiscal-years/<int:fy_id>/opening-stock/entry", methods=["POST"])
def opening_stock_entry(fy_id):
    from app.services import opening_stock

    fy = _fy(fy_id)
    with _errors():
        opening_stock.post(fy)
        db.session.commit()
    return _opening(fy, message="Écriture d'ouverture du stock passée, à valider.")
