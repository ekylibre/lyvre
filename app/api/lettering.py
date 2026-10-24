"""Lettrage des comptes de tiers (lot F3) et comptes par défaut (rôles)."""
from flask import jsonify, request
from flask_login import current_user

from app.access import instance_admin_required
from app.extensions import db
from app.models import Account, JournalLine, Lettering, Organization
from app.services import account_roles, lettering
from app.services.ledger_errors import LedgerError

from . import ApiError, bp, get_or_404, invalid, json_body, notice


@bp.route("/lettering/accounts")
def lettering_accounts():
    return jsonify(items=lettering.accounts(), gap_threshold_cents=lettering.gap_threshold())


@bp.route("/lettering/accounts/<int:account_id>/lines")
def lettering_lines(account_id):
    account = get_or_404(Account, account_id, "Compte introuvable.")
    state = request.args.get("state", "open")
    if state not in ("open", "lettered", "all"):
        raise invalid("État inconnu.", "state")
    return jsonify(account={"id": account.id, "code": account.code, "label": account.label,
                            "lettrable": account.lettrable},
                   items=[lettering.line_payload(line) for line in lettering.lines(account.id, state)],
                   open_balance_cents=lettering.open_balance(account.id))


@bp.route("/lettering/accounts/<int:account_id>/proposals")
def lettering_proposals(account_id):
    get_or_404(Account, account_id, "Compte introuvable.")
    return jsonify(items=lettering.proposals(account_id))


@bp.route("/lettering", methods=["POST"])
def lettering_create():
    """`{line_ids, gap}` : lettre les lignes (complet, partiel, ou avec écriture d'écart)."""
    data = json_body()
    ids = [i for i in data.get("line_ids") or [] if isinstance(i, int)]
    rows = JournalLine.query.filter(JournalLine.id.in_(ids)).all() if ids else []
    if len(rows) != len(set(ids)):
        raise ApiError("not_found", "Ligne introuvable.", 404)
    try:
        result = lettering.letter(rows, origin="auto" if data.get("proposal") else "manual",
                                  gap=bool(data.get("gap")), user_id=current_user.id)
    except LedgerError as exc:
        db.session.rollback()
        raise ApiError("conflict", str(exc), 409) from None
    db.session.commit()
    kind = "partiel" if result.partial else "complet"
    return jsonify(item={"id": result.id, "code": result.code, "partial": result.partial},
                   notices=[notice(f"Lettrage {result.code} ({kind}).")]), 201


@bp.route("/lettering/<int:lettering_id>", methods=["DELETE"])
def lettering_delete(lettering_id):
    item = get_or_404(Lettering, lettering_id, "Lettrage introuvable.")
    code = item.code
    try:
        lettering.unletter(item)
    except LedgerError as exc:
        db.session.rollback()
        raise ApiError("conflict", str(exc), 409) from None
    db.session.commit()
    return jsonify(notices=[notice(f"Lettrage {code} défait.")])


@bp.route("/lettering/reprise", methods=["POST"])
@instance_admin_required
def lettering_reprise():
    """Lettrage initial des factures de vente et d'achat déjà payées (une fois, après la mise à jour)."""
    result = lettering.reprise()
    db.session.commit()
    return jsonify(**result, notices=[notice(f"{result['letterings']} lettrage(s) créé(s).")])


# ------------------------------------------------------------------ comptes par défaut


@bp.route("/account-roles")
def account_roles_list():
    return jsonify(items=account_roles.listing(), lettering_gap_cents=lettering.gap_threshold())


@bp.route("/account-roles", methods=["PUT"])
@instance_admin_required
def account_roles_update():
    """`{roles: {role: account_id|null}, lettering_gap_cents}` (administrateur)."""
    data = json_body()
    try:
        for role, account_id in (data.get("roles") or {}).items():
            account_roles.set_role(role, account_id if isinstance(account_id, int) else None)
    except account_roles.RoleError as exc:
        db.session.rollback()
        raise invalid(str(exc), "roles") from None
    if "lettering_gap_cents" in data:
        gap = data["lettering_gap_cents"]
        if not isinstance(gap, int) or isinstance(gap, bool) or not 0 <= gap <= 10_000:
            raise invalid("Seuil entre 0 et 100 €.", "lettering_gap_cents")
        from app.services import organization
        organization.get().lettering_gap_cents = gap
    db.session.commit()
    return jsonify(items=account_roles.listing(), lettering_gap_cents=lettering.gap_threshold(),
                   notices=[notice("Comptes par défaut enregistrés.")])
