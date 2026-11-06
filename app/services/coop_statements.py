"""Décomptes de coopérative (lot AG10.d, claudedocs/design_efacturation_agricole.md § 4, AGD27, Q-E3).

Un décompte papier ou PDF (ou le détail d'une autofacture) se saisit ligne par ligne, chaque ligne typée :

| Type | Compte | Écriture |
|---|---|---|
| apport, complément de prix, ristourne | 70x de la production (compte de vente habituel, Q-E3) | crédit HT, TVA collectée 44571 |
| acompte déjà versé | — (déjà crédité au 411 par l'encaissement de l'acompte) | aucune ; réduit le net à payer |
| parts sociales retenues | 2621 | débit |
| cotisations, frais, prélèvements | 6x choisi | débit HT, TVA déductible 44566 |
| net du décompte | 411 du tiers | débit (crédit s'il est négatif) |

Une seule écriture équilibrée, au journal des ventes, à la date du décompte : compléments et ristournes vont
donc dans les ventes de l'exercice du décompte, même pour une campagne antérieure. Chaque ligne de vente peut
porter son activité et sa campagne (AG8) : ventilation analytique de la ligne (origine « coop »).

Comptes proposés à l'enregistrement quand la ligne n'en a pas : compte de la règle de l'activité, sinon
`self_billing.propose_account` (catalogue, désignation déjà reçue) ; 2621 pour les parts ; même libellé d'un
décompte précédent du tiers pour les frais.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Account, Activity, CoopStatement, CoopStatementLine, Entity
from app.models.coop_statement import LINE_KINDS, SALE_KINDS
from app.models.journal_entry import SOURCE_COOP_STATEMENT
from app.services import vat_codes
from app.services.import_activities import _words
from app.services.ledger import LedgerError
from app.services.sale_entry import SaleError, fiscal_year_for, parse_date, parse_decimal

SHARES_ACCOUNT = "2621"
VAT_COLLECTED = "44571"
VAT_DEDUCTIBLE = "44566"


def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal("1")))


# ------------------------------------------------------------------ totaux

def totals(st: CoopStatement) -> dict:
    out = {"sales_cents": 0, "sales_vat_cents": 0, "advances_cents": 0, "shares_cents": 0, "fees_cents": 0,
           "fees_vat_cents": 0}
    for line in st.lines:
        if line.kind in SALE_KINDS:
            out["sales_cents"] += line.amount_cents
            out["sales_vat_cents"] += line.vat_cents
        elif line.kind == "advance":
            out["advances_cents"] += line.amount_cents
        elif line.kind == "shares":
            out["shares_cents"] += line.amount_cents
        else:
            out["fees_cents"] += line.amount_cents
            out["fees_vat_cents"] += line.vat_cents
    out["customer_cents"] = (out["sales_cents"] + out["sales_vat_cents"] - out["shares_cents"] - out["fees_cents"]
                             - out["fees_vat_cents"])
    out["net_cents"] = out["customer_cents"] - out["advances_cents"]
    return out


# ------------------------------------------------------------------ comptes proposés

def _proposed(kind: str, label: str, entity: Entity, activity: Activity | None) -> Account | None:
    from app.services import self_billing
    if kind in SALE_KINDS:
        if activity is not None:
            account = self_billing.activity_account(activity)
            if account is not None:
                return account
        return self_billing.propose_account(label, entity)[0]
    if kind == "shares":
        return Account.query.filter_by(code=SHARES_ACCOUNT, is_header=False).first()
    if kind == "fee":
        words = _words(label)
        previous = (CoopStatementLine.query.join(CoopStatement)
                    .filter(CoopStatement.entity_id == entity.id, CoopStatementLine.kind == "fee",
                            CoopStatementLine.account_id.isnot(None))
                    .order_by(CoopStatement.statement_date.desc()).limit(200).all())
        return next((l.account for l in previous if _words(l.label) == words), None)
    return None


def _check_account(kind: str, account: Account, index: int) -> None:
    allowed = {"shares": ("26", "27"), "fee": ("6",)}.get(kind, ("7",))
    if account.is_header or not account.code.startswith(allowed):
        raise SaleError(f"Ligne {index} : compte « {account.code} » inadapté à « {LINE_KINDS[kind][0].lower()} » "
                        f"(compte {' ou '.join(a + '…' for a in allowed)}).", "lines")


# ------------------------------------------------------------------ saisie

def _entity(data: dict) -> Entity:
    raw = data.get("entity_id")
    entity = db.session.get(Entity, int(raw)) if str(raw or "").isdigit() else None
    if entity is None:
        raise SaleError("Choisissez la coopérative.", "entity_id")
    return entity


def _lines(rows, entity: Entity, day: date) -> list[CoopStatementLine]:
    from app.services import analytic
    if not isinstance(rows, list):
        raise SaleError("Lignes attendues.", "lines")
    lines = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "").strip()[:200]
        amount = parse_decimal(row.get("amount"), f"Montant de la ligne {index}", "lines")
        if not label and amount is None:
            continue
        kind = row.get("kind")
        if kind not in LINE_KINDS:
            raise SaleError(f"Ligne {index} : type de ligne inconnu.", "lines")
        if amount is None or amount <= 0:
            raise SaleError(f"Ligne {index} : montant HT positif attendu (le type donne le sens).", "lines")
        label = label or LINE_KINDS[kind][0]
        rate = parse_decimal(row.get("vat_rate"), f"Taux de TVA de la ligne {index}", "lines", Decimal(0)) or Decimal(0)
        if rate and kind in ("advance", "shares"):
            raise SaleError(f"Ligne {index} : pas de TVA sur « {LINE_KINDS[kind][0].lower()} ».", "lines")
        quantity = parse_decimal(row.get("quantity"), f"Quantité de la ligne {index}", "lines", Decimal(0))
        activity = None
        if str(row.get("activity_id") or "").isdigit():
            activity = db.session.get(Activity, int(row["activity_id"]))
            if activity is None:
                raise SaleError(f"Ligne {index} : activité introuvable.", "lines")
            if kind not in SALE_KINDS:
                raise SaleError(f"Ligne {index} : seule une ligne de vente porte une activité.", "lines")
        campaign = row.get("campaign_year")
        campaign = int(campaign) if str(campaign or "").isdigit() else None
        if activity is not None and campaign is None and kind == "delivery":
            campaign = analytic.campaign_year(activity, day)
        account = None
        code = str(row.get("account_code") or "").strip()
        if code and kind != "advance":
            account = Account.query.filter_by(code=code).first()
            if account is None:
                raise SaleError(f"Ligne {index} : compte « {code} » introuvable.", "lines")
            _check_account(kind, account, index)
        elif kind != "advance":
            account = _proposed(kind, label, entity, activity)
        cents = _round(amount * 100)
        bp = _round(rate * 100)
        lines.append(CoopStatementLine(
            position=len(lines), kind=kind, label=label, amount_cents=cents, vat_rate_bp=bp,
            vat_cents=_round(Decimal(cents) * bp / 10000),
            quantity_milli=_round(quantity * 1000) if quantity else None,
            unit=str(row.get("unit") or "").strip()[:20] or None, account_id=account.id if account else None,
            activity_id=activity.id if activity else None, campaign_year=campaign))
    if not lines:
        raise SaleError("Ajoutez au moins une ligne.", "lines")
    if not any(l.kind in SALE_KINDS for l in lines):
        raise SaleError("Un décompte porte au moins un apport, un complément de prix ou une ristourne.", "lines")
    return lines


def save(st: CoopStatement | None, data: dict) -> CoopStatement:
    if st is not None and st.status != "draft":
        raise SaleError("Décompte comptabilisé : repassez-le en brouillon pour le modifier.", status=409)
    entity = _entity(data)
    number = str(data.get("number") or "").strip()[:40]
    if not number:
        raise SaleError("Numéro du décompte obligatoire.", "number")
    day = parse_date(data.get("statement_date"), "Date du décompte", "statement_date")
    if day is None:
        raise SaleError("Date du décompte obligatoire.", "statement_date")
    other = CoopStatement.query.filter_by(entity_id=entity.id, number=number).first()
    if other is not None and (st is None or other.id != st.id):
        raise SaleError(f"Doublon : le décompte {number} de « {entity.name} » est déjà saisi.", "number", 409)
    lines = _lines(data.get("lines"), entity, day)
    if st is None:
        st = CoopStatement(status="draft")
        db.session.add(st)
    else:
        st.lines.clear()
        db.session.flush()
    st.entity, st.number, st.statement_date = entity, number, day
    st.label = str(data.get("label") or "").strip()[:200] or None
    st.lines = lines
    db.session.flush()
    token = data.get("attachment_token")
    if token:
        from app.services import attachments
        try:
            attachments.store(st, token, folder="decomptes", day=day)
        except attachments.AttachmentError as exc:
            raise SaleError(str(exc), "attachment_token") from None
    db.session.commit()
    return st


def delete(st: CoopStatement) -> None:
    if st.status != "draft":
        raise SaleError("Décompte comptabilisé : repassez-le en brouillon pour le supprimer.", status=409)
    from app.services import attachments
    path = attachments.path_of(st)
    db.session.delete(st)
    db.session.commit()
    if path is not None:
        path.unlink(missing_ok=True)


# ------------------------------------------------------------------ écriture

def problems(st: CoopStatement) -> list[str]:
    out = []
    fy = fiscal_year_for(st.statement_date)
    if fy is None:
        out.append(f"Aucun exercice ne couvre le {st.statement_date:%d/%m/%Y}.")
    elif fy.closed:
        out.append(f"L'exercice « {fy.label} » est clôturé.")
    elif not fy.vat_liable and any(l.vat_cents for l in st.lines):
        out.append("TVA sur une ligne alors que l'exercice n'est pas soumis à la TVA.")
    missing = [str(l.position + 1) for l in st.lines if l.kind != "advance" and l.account_id is None]
    if missing:
        out.append(f"Compte manquant (ligne {', '.join(missing)}).")
    return out


def entry_lines(st: CoopStatement, coded: bool) -> list[dict]:
    from app.services import sale_posting
    who = f"{st.entity.name} — décompte {st.number}"[:255]
    lines, collected, deductible = [], {}, {}
    for line in st.lines:
        direction = LINE_KINDS[line.kind][1]
        if direction is None:
            continue
        row = {"account_id": line.account_id, "label": f"{line.label} — {who}"[:255],
               "debit_cents": line.amount_cents if direction == "debit" else 0,
               "credit_cents": line.amount_cents if direction == "credit" else 0}
        if line.activity_id:
            row.update(analytic=f"activity:{line.activity_id}", analytic_origin="coop",
                       analytic_campaign=line.campaign_year)
        lines.append(row)
        if line.vat_cents:
            bucket = collected if direction == "credit" else deductible
            tax, base = bucket.get(line.vat_rate_bp, (0, 0))
            bucket[line.vat_rate_bp] = (tax + line.vat_cents, base + line.amount_cents)
    for rate, (tax, base) in sorted(collected.items(), key=lambda i: -i[0]):
        code = vat_codes.sale_tax_code(rate) if coded else None
        lines.append({"account_id": sale_posting.vat_account((VAT_COLLECTED, "TVA collectée")).id,
                      "label": f"TVA — {who}"[:255], "debit_cents": 0, "credit_cents": tax,
                      "vat_code": code, "vat_base_cents": base if code else None})
    for rate, (tax, base) in sorted(deductible.items(), key=lambda i: -i[0]):
        code = vat_codes.purchase_code("fr", "services", rate) if coded else None
        lines.append({"account_id": vat_codes.account(VAT_DEDUCTIBLE).id, "label": f"TVA déductible — {who}"[:255],
                      "debit_cents": tax, "credit_cents": 0, "vat_code": code, "vat_base_cents": base if code else None})
    customer = totals(st)["customer_cents"]
    if customer:
        lines.insert(0, {"account_id": sale_posting.customer_account(st.entity).id, "label": who,
                         "debit_cents": max(customer, 0), "credit_cents": max(-customer, 0)})
    return lines


def post(st: CoopStatement) -> CoopStatement:
    from app.services import sale_posting
    from app.services.ledger import post_entry
    if st.status != "draft":
        raise SaleError("Décompte déjà comptabilisé.", status=409)
    found = problems(st)
    if found:
        raise SaleError(" ".join(found), status=409)
    fy = fiscal_year_for(st.statement_date)
    try:
        entry = post_entry(
            fiscal_year_id=fy.id, journal_id=sale_posting._journal().id, entry_date=st.statement_date,  # noqa: SLF001
            description=f"Décompte {st.number} — {st.entity.name}"[:500], lines=entry_lines(st, fy.vat_liable),
            source=SOURCE_COOP_STATEMENT, source_ref=f"COOP:{st.id}", commit=False)
    except LedgerError as exc:
        db.session.rollback()
        raise SaleError(str(exc), status=409) from None
    st.journal_entry_id, st.status = entry.id, "posted"
    db.session.commit()
    return st


def unpost(st: CoopStatement) -> CoopStatement:
    """Retour en brouillon : l'écriture non validée est supprimée ; une écriture validée se contrepasse à la main."""
    from app.services.ledger import delete_entries
    if st.status != "posted":
        raise SaleError("Décompte non comptabilisé.", status=409)
    if st.journal_entry_id:
        result = delete_entries([st.journal_entry_id])[0]
        if result["status"] != "ok":
            db.session.rollback()
            raise SaleError(f"Écriture du décompte : {result.get('message', 'suppression impossible')}", status=409)
    st.journal_entry_id, st.status = None, "draft"
    db.session.commit()
    return st
