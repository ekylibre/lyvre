"""Livres de TVA (lot AG2.d) : livre des ventes, livre des achats, contrôle croisé avec la CA12A de la période.
Période : `?period=` (clé d'une déclaration, ex. « 2026-A ») ou `?start=&end=` ; défaut : période annuelle en cours."""
from flask import jsonify, request

from app.services import vat_books

from . import ApiError, bp


def _bounds():
    try:
        return vat_books.parse_bounds(request.args.get("start"), request.args.get("end"), request.args.get("period"))
    except vat_books.BookError as exc:
        raise ApiError("validation_error", exc.message, 422, {exc.field: exc.message} if exc.field else None) from None


def _iso_items(book: dict) -> dict:
    return {**book, "start": book["start"].isoformat(), "end": book["end"].isoformat(),
            "items": [{**i, "date": i["date"].isoformat()} for i in book["items"]]}


@bp.route("/vat-books/sales")
def vat_books_sales():
    start, end = _bounds()
    return jsonify(_iso_items(vat_books.sales_book(start, end)))


@bp.route("/vat-books/purchases")
def vat_books_purchases():
    start, end = _bounds()
    return jsonify(_iso_items(vat_books.purchases_book(start, end)))
