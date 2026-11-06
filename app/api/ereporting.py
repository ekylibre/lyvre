"""E-reporting B2C (lot AG10.e, claudedocs/design_efacturation_agricole.md § 6) : agrégats des ventes directes par
jour, catégorie et taux ; catégories de recette « vente directe » ; export JSON (SUPER PDP) et tableur. Instance
agricole seulement."""
import csv
import io
import json
from datetime import date

from flask import Response, jsonify, request
from flask_login import current_user

from app.models import EreportingExport, SimpleCategory
from app.services import ereporting
from app.services.ereporting import EreportingError

from . import ApiError, bp, invalid, json_body


def _agri_only():
    from app.tenant import is_agri
    if not is_agri():
        raise ApiError("not_found", "E-reporting : instance agricole seulement.", status=404)


def _period(source) -> tuple[date, date]:
    today = date.today()
    first = today.replace(day=1)
    try:
        start = date.fromisoformat(source.get("start")) if source.get("start") else first
        end = date.fromisoformat(source.get("end")) if source.get("end") else today
    except (TypeError, ValueError):
        raise invalid("Date invalide (AAAA-MM-JJ).", "start") from None
    if end < start:
        raise invalid("La fin précède le début.", "end")
    if (end - start).days > 366:
        raise invalid("Période d'un an au plus.", "end")
    return start, end


@bp.route("/ereporting")
def ereporting_view():
    _agri_only()
    start, end = _period(request.args)
    data = ereporting.aggregate(start, end)
    data["categories"] = [{"id": c.id, "label": c.label, "account": c.account.code, "direct_sale": c.direct_sale}
                          for c in SimpleCategory.query.filter_by(kind="income", active=True).order_by(SimpleCategory.position)]
    data["exports"] = [{"id": e.id, "start": e.start_date.isoformat(), "end": e.end_date.isoformat(),
                        "transactions": e.transactions, "base_cents": e.base_cents, "tax_cents": e.tax_cents,
                        "exported_at": e.exported_at.isoformat()}
                       for e in EreportingExport.query.order_by(EreportingExport.exported_at.desc()).limit(24)]
    return jsonify(data)


@bp.route("/ereporting/categories", methods=["PUT"])
def ereporting_categories():
    _agri_only()
    ids = json_body().get("ids")
    if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
        raise invalid("Liste de catégories attendue.", "ids")
    ereporting.set_categories(ids)
    return jsonify(notices=[{"level": "success", "message": "Catégories de vente directe enregistrées."}])


@bp.route("/ereporting/export", methods=["POST"])
def ereporting_export():
    """Export JSON de la période (corps de `POST /v1.beta/b2c_transactions`), noté comme exporté."""
    _agri_only()
    start, end = _period(json_body())
    try:
        body, _ = ereporting.record_export(start, end, getattr(current_user, "id", None))
    except EreportingError as exc:
        raise ApiError("conflict" if exc.status == 409 else "validation_error", exc.message, status=exc.status) from None
    return Response(json.dumps(body, ensure_ascii=False, indent=1), mimetype="application/json", headers={
        "Content-Disposition": f'attachment; filename="ereporting-b2c-{start}-{end}.json"'})


@bp.route("/ereporting/csv")
def ereporting_csv():
    _agri_only()
    start, end = _period(request.args)
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["Date", "Catégorie", "Taux (%)", "Base HT", "TVA"])
    for day in ereporting.aggregate(start, end)["days"]:
        for sub in day["subtotals"]:
            writer.writerow([day["date"], day["category"], f"{sub['rate_bp'] / 100:g}".replace(".", ","),
                             f"{sub['base_cents'] / 100:.2f}".replace(".", ","), f"{sub['tax_cents'] / 100:.2f}".replace(".", ",")])
    return Response("﻿" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="ereporting-b2c-{start}-{end}.csv"'})
