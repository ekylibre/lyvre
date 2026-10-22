"""Import d'un relevé OFX ; les factures d'achat saisies qu'il paie sont réglées."""
from flask import jsonify, request

from app.models import BankAccount
from app.services import purchase_settlement
from app.services.ofx_importer import import_ofx

from . import bp, get_or_404, invalid, notice


@bp.route("/imports/ofx", methods=["POST"])
def imports_ofx():
    """Multipart : `bank_account_id`, `ofx_file` (.ofx / .qfx, OFX 1.x SGML ou 2.x XML)."""
    bank_account_id = request.form.get("bank_account_id", type=int)
    if not bank_account_id:
        raise invalid("Choisissez un compte bancaire.", "bank_account_id")
    ba = get_or_404(BankAccount, bank_account_id, "Compte bancaire introuvable.")
    file = request.files.get("ofx_file")
    if not file or not file.filename:
        raise invalid("Choisissez un fichier OFX.", "ofx_file")
    try:
        result = import_ofx(file.stream, ba.id)
    except Exception as exc:  # noqa: BLE001 — fichier illisible : message à l'écran
        raise invalid(f"Fichier OFX illisible : {exc}", "ofx_file") from None
    notices = [notice(f"{result['imported']} transaction(s) importée(s), {result['duplicates']} doublon(s) ignoré(s).",
                      "warning" if result["errors"] else "success")]
    matching = {"matched": 0, "settled": 0, "errors": []}
    if result["imported"]:
        # Factures d'achat saisies en attente : débit unique de même montant → réglées.
        matching = purchase_settlement.auto_match()
        if matching["matched"]:
            notices.append(notice(f"{matching['matched']} facture(s) d'achat rattachée(s) à leur paiement, "
                                  f"{matching['settled']} règlement(s) passé(s)."))
        notices += [notice(e, "danger") for e in matching["errors"]]
    return jsonify(result={"imported": result["imported"], "duplicates": result["duplicates"],
                           "errors": result["errors"], "matched": matching["matched"],
                           "settled": matching["settled"]}, notices=notices)
