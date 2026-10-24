"""Reprise d'historique (lot F6) : import d'un FEC (historique complet ou soldes d'ouverture) et
d'écritures d'un tableur ; correspondances de comptes et profils mémorisés. Administrateur."""
import json
from datetime import date

from flask import jsonify, request
from flask_login import current_user

from app.access import instance_admin_required
from app.extensions import db
from app.models import AccountMapping, FiscalYear, ImportProfile
from app.services import fec_import, sheet_import
from app.services.ledger_errors import LedgerError

from . import ApiError, bp, get_or_404, invalid, notice


def _file():
    file = request.files.get("file")
    if not file or not file.filename:
        raise invalid("Choisissez un fichier.", "file")
    return file.filename, file.read()


def _json_field(name):
    raw = request.form.get(name)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except ValueError:
        raise invalid("Données invalides.", name) from None
    return value if isinstance(value, dict) else {}


def _overrides():
    return {k: v for k, v in _json_field("mappings").items() if isinstance(v, int)}


def _failure(exc):
    db.session.rollback()
    return ApiError("import_refused", str(exc), 409, extra={"problems": getattr(exc, "problems", [])[:50]})


def _day(name):
    try:
        return date.fromisoformat(request.form.get(name) or "")
    except ValueError:
        raise invalid("Date invalide.", name) from None


@bp.route("/imports/fec/analyze", methods=["POST"])
@instance_admin_required
def imports_fec_analyze():
    filename, content = _file()
    try:
        return jsonify(fec_import.analyze(content, filename, _overrides()))
    except LedgerError as exc:
        raise _failure(exc) from None


@bp.route("/imports/fec", methods=["POST"])
@instance_admin_required
def imports_fec():
    """Multipart : `file`, `mode` (`history` : `start_date`, `end_date` ; `opening` : `fiscal_year_id`), `mappings`."""
    filename, content = _file()
    mode = request.form.get("mode")
    try:
        if mode == "history":
            result = fec_import.import_history(content, filename, _day("start_date"), _day("end_date"), _overrides(),
                                               current_user.id)
            message = f"{result['entries']} écriture(s) importée(s) dans l'exercice {result['fiscal_year']}, validées et verrouillées."
        elif mode == "opening":
            fy = get_or_404(FiscalYear, request.form.get("fiscal_year_id", type=int), "Exercice introuvable.")
            result = fec_import.import_opening(content, filename, fy, _overrides(), current_user.id)
            message = f"À-nouveaux repris ({result['reference']}, {result['lines']} ligne(s))."
        else:
            raise invalid("Mode inconnu.", "mode")
    except LedgerError as exc:
        raise _failure(exc) from None
    return jsonify(**result, notices=[notice(message)])


@bp.route("/imports/sheet/analyze", methods=["POST"])
@instance_admin_required
def imports_sheet_analyze():
    filename, content = _file()
    try:
        return jsonify(**sheet_import.analyze(content, filename, _json_field("columns") or None, _overrides()),
                       profiles=sheet_import.profiles())
    except LedgerError as exc:
        raise _failure(exc) from None


@bp.route("/imports/sheet", methods=["POST"])
@instance_admin_required
def imports_sheet():
    filename, content = _file()
    try:
        result = sheet_import.run(content, filename, _json_field("columns"), _overrides(),
                                  (request.form.get("profile_name") or "").strip() or None, current_user.id)
    except LedgerError as exc:
        raise _failure(exc) from None
    return jsonify(**result, notices=[notice(f"{result['entries']} écriture(s) importée(s) en brouillard.")])


@bp.route("/import-profiles")
@instance_admin_required
def import_profiles():
    return jsonify(items=sheet_import.profiles())


@bp.route("/import-profiles/<int:profile_id>", methods=["DELETE"])
@instance_admin_required
def import_profiles_delete(profile_id):
    db.session.delete(get_or_404(ImportProfile, profile_id, "Profil introuvable."))
    db.session.commit()
    return jsonify(notices=[notice("Profil supprimé.")])


@bp.route("/account-mappings")
@instance_admin_required
def account_mappings():
    return jsonify(items=[{"id": m.id, "source_code": m.source_code, "account_code": m.account.code,
                           "account_label": m.account.label} for m in AccountMapping.query.order_by(AccountMapping.source_code)])


@bp.route("/account-mappings/<int:mapping_id>", methods=["DELETE"])
@instance_admin_required
def account_mappings_delete(mapping_id):
    db.session.delete(get_or_404(AccountMapping, mapping_id, "Correspondance introuvable."))
    db.session.commit()
    return jsonify(notices=[notice("Correspondance supprimée.")])
