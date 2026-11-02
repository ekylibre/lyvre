"""Comptes bancaires : liste, création, modification, suppression ; rattachement et
synchronisation Qonto ; contreparties à valider ; contexte de l'espace de rapprochement.
Les transactions sont servies par reconciliation.py (`/bank-accounts/<id>/transactions`)."""
from datetime import date

from flask import current_app, jsonify, request, url_for

from app.access import instance_admin_required
from app.extensions import db
from app.models import Account, BankAccount, Entity, Journal
from app.services import bank_balance, cash, counterparties, external_config, qonto_sync
from app.tenant import current_chart
from app.utils.list_filters import month_options_for_fy

from . import ApiError, bp, get_or_404, invalid, json_body, notice, require_integration
from .session import job_payload


def _iso(value):
    return value.isoformat() if value else None


def bank_account_payload(ba: BankAccount, stats=True, fy=False) -> dict:
    """`fy` : exercice du solde bancaire (False : exercice affiché, recherché ici)."""
    payload = {
        "id": ba.id, "label": ba.label, "iban": ba.iban, "kind": ba.kind,
        "account": {"id": ba.account.id, "code": ba.account.code, "label": ba.account.label},
        "qonto": {"account_id": ba.qonto_account_id, "sync_from": _iso(ba.qonto_sync_from),
                  "synced_at": _iso(ba.qonto_synced_at)} if ba.qonto_account_id else None,
    }
    if stats:
        payload["transactions"] = ba.transactions.count()
        payload["unreconciled"] = ba.transactions.filter_by(reconciled=False).count()
        payload["balance_cents"] = cash.ledger_balance(ba.account_id, date.today())
        if ba.kind == "bank":
            fy = bank_balance.display_fiscal_year() if fy is False else fy
            payload["bank_balance"] = bank_balance.bank_balance(ba, fy)
    return payload


def _gl_accounts(prefix="51"):
    return (Account.query.filter(Account.code.like(f"{prefix}%"), Account.is_header.is_(False))
            .order_by(Account.code).all())


def _options(prefix="51"):
    return [{"value": str(a.id), "label": f"{a.code} — {a.label}"} for a in _gl_accounts(prefix)]


@bp.route("/bank-accounts")
def bank_accounts_list():
    accounts = BankAccount.query.order_by(BankAccount.label).all()
    fy = bank_balance.display_fiscal_year()
    return jsonify(items=[bank_account_payload(ba, fy=fy) for ba in accounts], meta={
        "gl_accounts": _options(), "cash_accounts": _options("53"),
        "qonto": external_config.state("qonto", "transactions"),
    })


def _apply(ba: BankAccount, data: dict) -> None:
    label = str(data.get("label") or "").strip()
    if not label:
        raise invalid("Le libellé est obligatoire.", "label")
    try:
        account_id = int(data.get("account_id"))
    except (TypeError, ValueError):
        account_id = None
    kind = data.get("kind") or ba.kind or "bank"
    if kind not in ("bank", "cash"):
        raise invalid("Nature inconnue (banque ou caisse).", "kind")
    if ba.id is not None and kind != ba.kind and (ba.transactions.count() or ba.qonto_account_id):
        raise invalid("Un compte bancaire avec des transactions ou lié à Qonto ne devient pas une caisse.", "kind")
    prefix, what = ("53", "de caisse (53…)") if kind == "cash" else ("51", "de banque (51…)")
    account = db.session.get(Account, account_id) if account_id else None
    if account is None or not account.code.startswith(prefix) or account.is_header:
        raise invalid(f"Choisissez un compte {what}.", "account_id")
    iban = str(data.get("iban") or "").strip().upper().replace(" ", "")
    if len(iban) > 34:
        raise invalid("IBAN trop long (34 caractères au plus).", "iban")
    if kind == "cash":
        iban = ""
    ba.label, ba.iban, ba.account_id, ba.kind = label[:200], iban or None, account.id, kind


@bp.route("/bank-accounts", methods=["POST"])
def bank_accounts_create():
    ba = BankAccount()
    _apply(ba, json_body())
    db.session.add(ba)
    db.session.commit()
    return jsonify(item=bank_account_payload(ba), notices=[notice(f"Compte bancaire « {ba.label} » créé.")]), 201


@bp.route("/bank-accounts/<int:ba_id>")
def bank_accounts_detail(ba_id):
    """Compte, synchronisation Qonto, contreparties à valider, transactions annulées encore rapprochées."""
    ba = get_or_404(BankAccount, ba_id, "Compte bancaire introuvable.")
    job = qonto_sync.latest_job(ba.id) if ba.qonto_account_id else None
    reversed_reconciled = ba.transactions.filter_by(is_reversed=True, reconciled=True).all()
    return jsonify(
        item=bank_account_payload(ba),
        qonto_job=job_payload(job) if job else None,
        proposal_count=counterparties.count_proposals(ba.id),
        reversed_reconciled=[{
            "id": t.id, "date": t.transaction_date.isoformat(), "label": t.label or "",
            "amount_cents": t.amount_cents,
            "entry": ({"reference": t.journal_line.entry.reference,
                       "url": url_for("entries.detail", entry_id=t.journal_line.entry_id)}
                      if t.journal_line else None)} for t in reversed_reconciled],
        meta={"gl_accounts": _options(), "months": month_options_for_fy(),
              "qonto": external_config.state("qonto", "transactions")},
    )


@bp.route("/bank-accounts/<int:ba_id>", methods=["PATCH"])
def bank_accounts_update(ba_id):
    ba = get_or_404(BankAccount, ba_id, "Compte bancaire introuvable.")
    _apply(ba, json_body())
    db.session.commit()
    return jsonify(item=bank_account_payload(ba), notices=[notice("Compte bancaire mis à jour.")])


@bp.route("/bank-accounts/<int:ba_id>", methods=["DELETE"])
def bank_accounts_delete(ba_id):
    ba = get_or_404(BankAccount, ba_id, "Compte bancaire introuvable.")
    count = ba.transactions.count()
    if count:
        raise ApiError("conflict", f"Impossible de supprimer « {ba.label} » : {count} transaction(s) associée(s).",
                       status=409)
    statements = ba.statements.count()
    if statements:  # relevés conservés (personne ne les supprime)
        raise ApiError("conflict", f"Impossible de supprimer « {ba.label} » : {statements} relevé(s) de compte conservé(s).",
                       status=409)
    db.session.delete(ba)
    db.session.commit()
    return jsonify(notices=[notice(f"Compte bancaire « {ba.label} » supprimé.")])


# ------------------------------------------------------------------ solde bancaire d'ouverture


@bp.route("/bank-accounts/<int:ba_id>/opening")
def bank_accounts_opening(ba_id):
    """Solde bancaire d'ouverture, date proposée et contreparties de l'écriture d'apport initial."""
    ba = get_or_404(BankAccount, ba_id, "Compte bancaire introuvable.")
    return jsonify(item=bank_balance.opening_payload(ba),
                   meta={"counterparts": bank_balance.counterpart_options(current_chart())})


@bp.route("/bank-accounts/<int:ba_id>/opening", methods=["PUT"])
def bank_accounts_opening_set(ba_id):
    """Saisit le solde d'ouverture (`amount_cents`, `date`), et l'écriture d'apport si `post_entry`
    (`counterpart` : id du compte, ou `new:<code>`) ; `amount_cents` nul : solde retiré."""
    ba = get_or_404(BankAccount, ba_id, "Compte bancaire introuvable.")
    try:
        entry = bank_balance.set_opening(ba, json_body(), current_chart())
    except bank_balance.BankBalanceError as exc:
        if exc.field and exc.status == 422:
            raise invalid(exc.message, exc.field) from None
        raise ApiError("conflict" if exc.status == 409 else "validation_error", exc.message,
                       status=exc.status) from None
    notices = [notice("Solde bancaire d'ouverture enregistré." if ba.opening_balance_date
                      else "Solde bancaire d'ouverture retiré.")]
    if entry is not None:
        notices.append(notice(f"Écriture d'apport initial {entry.reference} passée."))
    return jsonify(item=bank_account_payload(ba), opening=bank_balance.opening_payload(ba), notices=notices)


# ------------------------------------------------------------------ Qonto


def _qonto_accounts():
    """(comptes Qonto de l'API, message d'erreur) — aucun appel si l'intégration est indisponible.
    Lecture seule (GET des comptes de l'organisation)."""
    if not external_config.scope_available("qonto", "transactions"):
        return [], external_config.unavailable_message("qonto")
    from app.services import integrations, qonto_client

    try:
        return qonto_client.from_app_config().bank_accounts(), None
    except Exception as exc:  # noqa: BLE001 — message lisible pour l'écran
        return [], integrations.mask_secrets("qonto", integrations.describe_error("qonto", exc))


def _date(value, field):
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        raise invalid("Date invalide.", field) from None


@bp.route("/qonto/accounts")
@instance_admin_required
def qonto_accounts():
    accounts, error = _qonto_accounts()
    gl = _gl_accounts()
    default_gl = next((a for a in gl if a.code.startswith("512")), None)
    return jsonify(
        items=[{"qonto_id": a.qonto_id, "name": a.name, "iban": a.iban, "status": a.status, "main": a.main,
                "closed": a.is_closed, "balance_cents": a.balance_cents,
                "linked": bank_account_payload(a.linked, stats=False) if a.linked else None,
                "proposed_id": a.proposed.id if a.proposed else None}
               for a in qonto_sync.list_accounts(accounts)],
        error=error,
        meta={"gl_accounts": _options(), "default_gl_id": default_gl.id if default_gl else None,
              "unlinked": [{"value": str(b.id), "label": b.label} for b in
                           BankAccount.query.filter(BankAccount.qonto_account_id.is_(None), BankAccount.kind == "bank")
                           .order_by(BankAccount.label)],
              "default_sync_from": qonto_sync.default_sync_from().isoformat()},
    )


@bp.route("/qonto/accounts/link", methods=["POST"])
@instance_admin_required
def qonto_link():
    """`{qonto_account_id, mode: existing|new, bank_account_id | label + gl_account_id, sync_from}`."""
    data = json_body()
    accounts, error = _qonto_accounts()
    if error:
        raise ApiError("conflict", error, status=409)
    qonto_account = next((a for a in accounts if a.get("id") == data.get("qonto_account_id")), None)
    if qonto_account is None:
        raise ApiError("not_found", "Compte Qonto introuvable.", status=404)
    sync_from = _date(data.get("sync_from"), "sync_from")
    try:
        if data.get("mode") == "existing":
            ba = qonto_sync.link_account(qonto_account, bank_account_id=data.get("bank_account_id") and int(data["bank_account_id"]),
                                         sync_from=sync_from)
        else:
            ba = qonto_sync.link_account(qonto_account, label=data.get("label"),
                                         gl_account_id=data.get("gl_account_id") and int(data["gl_account_id"]),
                                         sync_from=sync_from)
    except (qonto_sync.QontoLinkError, ValueError) as exc:
        raise invalid(str(exc)) from None
    return jsonify(item=bank_account_payload(ba), notices=[notice(
        f"Compte Qonto rattaché à « {ba.label} » (synchronisation à partir du "
        f"{ba.qonto_sync_from.strftime('%d/%m/%Y')}).")])


@bp.route("/bank-accounts/<int:ba_id>/qonto", methods=["DELETE"])
@instance_admin_required
def qonto_unlink(ba_id):
    ba = get_or_404(BankAccount, ba_id, "Compte bancaire introuvable.")
    qonto_sync.unlink_account(ba)
    return jsonify(item=bank_account_payload(ba), notices=[notice(
        f"« {ba.label} » n'est plus rattaché à Qonto (transactions conservées).")])


@bp.route("/bank-accounts/<int:ba_id>/qonto", methods=["PATCH"])
@instance_admin_required
def qonto_settings(ba_id):
    """`{sync_from}` : reculer la date relance une synchronisation complète (sans doublon)."""
    ba = get_or_404(BankAccount, ba_id, "Compte bancaire introuvable.")
    if not ba.qonto_account_id:
        raise ApiError("conflict", "Ce compte bancaire n'est pas rattaché à Qonto.", status=409)
    sync_from = _date(json_body().get("sync_from"), "sync_from")
    qonto_sync.set_sync_from(ba, sync_from)
    return jsonify(item=bank_account_payload(ba), notices=[notice(
        f"Synchronisation Qonto à partir du {sync_from.strftime('%d/%m/%Y')}.")])


@bp.route("/bank-accounts/<int:ba_id>/qonto/sync", methods=["POST"])
def qonto_sync_start(ba_id):
    """Synchronisation en arrière-plan (lecture des transactions Qonto) ; suivi par /jobs/<id>."""
    ba = get_or_404(BankAccount, ba_id, "Compte bancaire introuvable.")
    if not ba.qonto_account_id:
        raise ApiError("conflict", "Ce compte bancaire n'est pas rattaché à Qonto.", status=409)
    require_integration("qonto", "transactions")
    job = qonto_sync.start_sync(current_app._get_current_object(), ba.id)
    return jsonify(job=job_payload(job))


# ------------------------------------------------------------------ contreparties


@bp.route("/bank-accounts/<int:ba_id>/counterparties")
def counterparties_list(ba_id):
    ba = get_or_404(BankAccount, ba_id, "Compte bancaire introuvable.")
    return jsonify(
        items=[{"key": p.key, "label": p.label, "count": p.count, "total_cents": p.total_cents,
                "first_date": _iso(p.first_date), "last_date": _iso(p.last_date)}
               for p in counterparties.proposals(ba.id)],
        meta={"bank_account": bank_account_payload(ba, stats=False),
              "entities": [{"value": str(e.id), "label": e.name} for e in Entity.query.order_by(Entity.name)]},
    )


@bp.route("/counterparties", methods=["POST"])
def counterparties_decide():
    """`{action: create|link|ignore, key, label, name?, entity_id?}`."""
    data = json_body()
    action, key, label = data.get("action"), str(data.get("key") or ""), str(data.get("label") or "")
    if not key:
        raise invalid("Contrepartie manquante.")
    try:
        if action == "ignore":
            counterparties.ignore(key, label)
            return jsonify(notices=[notice(f"« {label} » ne sera plus proposé.")])
        if action == "link":
            entity, n, _ = counterparties.accept(key, entity_id=data.get("entity_id") and int(data["entity_id"]))
            return jsonify(notices=[notice(f"{n} transaction(s) rattachée(s) à « {entity.name} ».")])
        if action == "create":
            entity, n, _ = counterparties.accept(key, create_name=data.get("name"))
            return jsonify(notices=[notice(f"Fournisseur « {entity.name} » : {n} transaction(s) rattachée(s).")])
    except ValueError as exc:
        raise invalid(str(exc)) from None
    raise invalid("Action inconnue.", "action")


# ------------------------------------------------------------------ rapprochement


@bp.route("/reconciliation/context")
def reconciliation_context():
    """Comptes bancaires, mois de l'exercice et journal par défaut de l'espace de rapprochement."""
    bq = Journal.query.filter_by(code="BQ").first()
    return jsonify(
        bank_accounts=[bank_account_payload(ba, stats=False)
                       for ba in BankAccount.query.filter_by(kind="bank").order_by(BankAccount.label)],
        months=month_options_for_fy(), default_journal_id=bq.id if bq else None,
    )
