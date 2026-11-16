"""Documents de l'instance (lot NV5, claudedocs/design_navigation.md § 6) : navigateur en lecture seule.
Les fichiers sont servis par les routes existantes de chaque source (`file_url`)."""
from flask import jsonify, request

from app.services import documents

from . import ApiError, bp


@bp.route("/documents")
def documents_index():
    kind = request.args.get("kind") or None
    if kind and kind not in documents.BY_KIND:
        raise ApiError("validation_error", "Type de document inconnu.", status=422, fields={"kind": "Type inconnu."})
    fy = request.args.get("fiscal_year") or None
    try:
        fy_id = int(fy) if fy else None
    except ValueError:
        raise ApiError("validation_error", "Exercice invalide.", status=422, fields={"fiscal_year": "Exercice invalide."})
    page = request.args.get("page", 1, type=int) or 1
    return jsonify(documents.browse(kind=kind, fiscal_year_id=fy_id, q=request.args.get("q"), page=page))
