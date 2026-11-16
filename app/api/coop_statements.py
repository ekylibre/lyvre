"""Décomptes de coopérative (lot AG10.d, claudedocs/design_efacturation_agricole.md § 4) : liste, saisie
(lignes typées, compte proposé, activité et campagne), écriture unique au journal des ventes, retour en
brouillon, pièce jointe. Instance agricole seulement."""
from contextlib import contextmanager

from flask import jsonify, request, send_file

from app.extensions import db
from app.models import Account, Activity, Associate, CoopStatement, Entity, Journal
from app.models.coop_statement import LINE_KINDS, STATUSES
from app.services import attachments, coop_statements
from app.services.sale_entry import SaleError

from . import ApiError, bp, get_or_404, invalid, json_body, notice


def _agri_only():
    from app.tenant import is_agri
    if not is_agri():
        raise ApiError("not_found", "Décomptes de coopérative : instance agricole seulement.", status=404)


@contextmanager
def _errors():
    try:
        yield
    except SaleError as exc:
        db.session.rollback()
        if exc.status == 422:
            raise invalid(exc.message, exc.field) from None
        raise ApiError("conflict" if exc.status == 409 else "not_found", exc.message, status=exc.status) from None


def _money(cents: int) -> str:
    return f"{cents / 100:.2f}".replace(".", ",")


def _row(st: CoopStatement) -> dict:
    return {"id": st.id, "number": st.number, "statement_date": st.statement_date.isoformat(), "label": st.label or "",
            "status": st.status, "status_label": STATUSES[st.status],
            "entity": {"id": st.entity_id, "name": st.entity.name}, **coop_statements.totals(st)}


def _detail(st: CoopStatement) -> dict:
    return {**_row(st), "entity_id": str(st.entity_id), "journal_code": st.journal.code if st.journal else "",
            "lines": [{"id": l.id, "kind": l.kind, "label": l.label, "amount": _money(l.amount_cents),
                       "amount_cents": l.amount_cents, "vat_rate": f"{l.vat_rate_bp / 100:g}".replace(".", ","),
                       "vat_cents": l.vat_cents,
                       "quantity": f"{l.quantity_milli / 1000:g}".replace(".", ",") if l.quantity_milli else "",
                       "unit": l.unit or "", "account_code": l.account.code if l.account else "",
                       "activity_id": str(l.activity_id or ""), "campaign_year": str(l.campaign_year or "")}
                      for l in st.lines],
            "problems": coop_statements.problems(st) if st.status == "draft" else [],
            "journal_entry": {"id": st.journal_entry_id, "reference": st.journal_entry.reference}
            if st.journal_entry else None,
            "attachment": {"name": st.attachment_name, "url": f"/api/v1/coop-statements/{st.id}/attachment"}
            if st.attachment_path else None}


@bp.route("/coop-statements")
def coop_statements_list():
    _agri_only()
    rows = CoopStatement.query.order_by(CoopStatement.statement_date.desc(), CoopStatement.id.desc()).limit(500).all()
    return jsonify(items=[_row(st) for st in rows])


def _entities() -> list[dict]:
    """Coopératives d'abord (journal propre ou décompte déjà saisi), puis clients, puis autres tiers ; sans les associés.
    `journal` : journal proposé pour le décompte."""
    journals = coop_statements.suggested_journals()
    used = {i for (i,) in db.session.query(CoopStatement.entity_id).distinct()}
    last = {st.entity_id: st.journal.code for st in CoopStatement.query.order_by(CoopStatement.id) if st.journal}
    associates = {i for (i,) in db.session.query(Associate.entity_id)}
    out = []
    for e in Entity.query.order_by(Entity.name):
        if e.id in associates:
            continue
        journal = last.get(e.id) or journals.get(e.id) or "VE"
        group = ("Coopératives et négoces" if e.id in used or journal != "VE"
                 else "Clients" if e.customer_account_code else "Autres tiers")
        out.append({"value": str(e.id), "label": e.name, "group": group, "journal": journal})
    order = {"Coopératives et négoces": 0, "Clients": 1, "Autres tiers": 2}
    return sorted(out, key=lambda x: order[x["group"]])


@bp.route("/coop-statements/form-options")
def coop_statements_options():
    _agri_only()
    accounts = (Account.query.filter(Account.is_header.is_(False), db.or_(Account.code.like("7%"), Account.code.like("6%"),
                                                                         Account.code.like("26%")))
                .order_by(Account.code))
    return jsonify(
        entities=_entities(),
        journals=[{"value": j.code, "label": f"{j.code} — {j.label}"} for j in Journal.query.order_by(Journal.code)
                  if j.code not in coop_statements.NOT_COOP_JOURNALS],
        kinds=[{"value": k, "label": label} for k, (label, _) in LINE_KINDS.items()],
        accounts=[{"value": a.code, "label": f"{a.code} — {a.label}"} for a in accounts],
        activities=[{"value": str(a.id), "label": a.name}
                    for a in Activity.query.filter_by(archived=False).order_by(Activity.name)])


@bp.route("/coop-statements", methods=["POST"])
def coop_statements_create():
    _agri_only()
    with _errors():
        st = coop_statements.save(None, json_body())
    return jsonify(item=_detail(st), notices=[notice(f"Décompte {st.number} enregistré en brouillon.")]), 201


@bp.route("/coop-statements/<int:statement_id>")
def coop_statements_detail(statement_id):
    _agri_only()
    return jsonify(item=_detail(get_or_404(CoopStatement, statement_id, "Décompte introuvable.")))


@bp.route("/coop-statements/<int:statement_id>", methods=["PUT"])
def coop_statements_update(statement_id):
    _agri_only()
    st = get_or_404(CoopStatement, statement_id, "Décompte introuvable.")
    with _errors():
        coop_statements.save(st, json_body())
    return jsonify(item=_detail(st), notices=[notice("Décompte enregistré.")])


@bp.route("/coop-statements/<int:statement_id>", methods=["DELETE"])
def coop_statements_delete(statement_id):
    _agri_only()
    st = get_or_404(CoopStatement, statement_id, "Décompte introuvable.")
    with _errors():
        coop_statements.delete(st)
    return jsonify(notices=[notice("Décompte supprimé.")])


@bp.route("/coop-statements/<int:statement_id>/post", methods=["POST"])
def coop_statements_post(statement_id):
    _agri_only()
    st = get_or_404(CoopStatement, statement_id, "Décompte introuvable.")
    with _errors():
        coop_statements.post(st)
    return jsonify(item=_detail(st), notices=[notice(
        f"Décompte {st.number} comptabilisé (écriture {st.journal_entry.reference}).")])


@bp.route("/coop-statements/<int:statement_id>/unpost", methods=["POST"])
def coop_statements_unpost(statement_id):
    _agri_only()
    st = get_or_404(CoopStatement, statement_id, "Décompte introuvable.")
    with _errors():
        coop_statements.unpost(st)
    return jsonify(item=_detail(st), notices=[notice(f"Décompte {st.number} repassé en brouillon, écriture supprimée.")])


@bp.route("/coop-statements/<int:statement_id>/attachment")
def coop_statements_attachment(statement_id):
    _agri_only()
    st = get_or_404(CoopStatement, statement_id, "Décompte introuvable.")
    path = attachments.path_of(st)
    if path is None:
        raise ApiError("not_found", "Pièce introuvable.", status=404)
    return send_file(path, mimetype=st.attachment_mime or "application/pdf",
                     as_attachment=request.args.get("download") == "1", download_name=st.attachment_name or path.name)
