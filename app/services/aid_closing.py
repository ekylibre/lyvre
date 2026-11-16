"""Aides à la clôture (lot AG3.c, claudedocs/design_aides_pac.md § 4, AGD19 et AGD20).

Au réel en partie double, pour chaque dossier d'exploitation (part d'exploitation d'une aide mixte) :
- fait générateur au plus tard à la clôture : **produit à recevoir** = acquis − versé à la clôture, D 441 / C compte de
  l'aide (PCG 618-6 pour les aides PAC, décision d'attribution pour les autres) ;
- versé avant un fait générateur postérieur à la clôture : **produit constaté d'avance**, D compte de l'aide / C 487 ;
- versé au-delà de l'acquis, décision non datée, ventilation manquante : signalés, sans écriture.

Les écritures sont des écritures d'inventaire (`closing.add_inventory`, extournées à l'ouverture de N+1) repérées par
leur `source_ref` ; un montant différent du calcul exige un motif, une proposition écartée aussi (`aid_accruals`).
Au micro-BA (comptabilité simplifiée), rien : les aides y sont prises à l'encaissement.
"""
from __future__ import annotations

from app.extensions import db
from app.models import Aid, AidAccrual, JournalEntry
from app.services import aids
from app.services.aids import AidError

MIN_REASON = 5
KINDS = {"accrued": ("accrued_income", "441", "Aide à recevoir"),
         "deferred": ("deferred_income", "487", "Aide perçue d'avance")}


def enabled() -> bool:
    from app.services.rule_entries import simple_mode
    from app.tenant import is_agri

    return is_agri() and not simple_mode()


def _key(kind: str, aid_id: int) -> str:
    return f"aid:{aid_id}" if kind == "accrued" else f"aid-deferred:{aid_id}"


def _posted(fy) -> dict[str, JournalEntry]:
    from app.models.journal_entry import SOURCE_INVENTORY

    rows = JournalEntry.query.filter(JournalEntry.fiscal_year_id == fy.id, JournalEntry.source == SOURCE_INVENTORY,
                                     JournalEntry.source_ref.like("aid%")).all()
    return {e.source_ref: e for e in rows}


def _entry_amount(entry: JournalEntry) -> int:
    return sum(line.debit_cents for line in entry.lines)


def _operating_share(aid: Aid) -> tuple[float | None, str | None]:
    if aid.nature == "operating":
        return 1.0, None
    total = aids.acquired_cents(aid)
    if aid.investment_share_cents is None or not total:
        return None, "Ventilation à saisir (part d'investissement) : part d'exploitation inconnue."
    return max(total - aid.investment_share_cents, 0) / total, None


def proposals(fy) -> dict:
    """{items, issues} : propositions de l'exercice (passées ou non) et dossiers à compléter."""
    if not enabled():
        return {"items": [], "issues": []}
    posted = _posted(fy)
    decisions = {d.aid_id: d for d in AidAccrual.query.filter_by(fiscal_year_id=fy.id)}
    items, issues = [], []
    years = {fy.start_date.year, fy.end_date.year}
    for aid in Aid.query.filter(Aid.nature.in_(("operating", "mixed")), Aid.status.notin_(("refused", "closed")),
                                Aid.campaign <= fy.end_date.year).order_by(Aid.campaign, Aid.id):
        if aid.trigger == "payment":
            continue
        label = f"{aid.label} {aid.campaign}"
        on, provisional = aids.trigger_date(aid)
        if on is None:
            if aid.campaign in years:
                issues.append({"aid_id": aid.id, "label": label, "message": "Date de la décision d'attribution à saisir."})
            continue
        share, problem = _operating_share(aid)
        if share is None:
            if aid.campaign in years:
                issues.append({"aid_id": aid.id, "label": label, "message": problem})
            continue
        acquired = round(aids.acquired_cents(aid) * share)
        paid = round(aids.paid_cents(aid, fy.end_date) * share)
        account = aid.operating_account if aid.nature == "mixed" else aid.account
        if on <= fy.end_date:
            kind, amount = "accrued", acquired - paid
            if amount < 0:
                issues.append({"aid_id": aid.id, "label": label,
                               "message": f"Versé au-delà de l'acquis ({-amount / 100:.2f} €) : reversement à prévoir "
                                          "ou montant notifié à saisir.".replace(".", ",", 1)})
                continue
        else:
            kind, amount = "deferred", paid
        key = _key(kind, aid.id)
        entry = posted.get(key)
        decision = decisions.get(aid.id)
        if amount <= 0 and entry is None:
            continue
        dismissed = decision is not None and decision.status == "dismissed" and entry is None
        items.append({
            "key": key, "aid_id": aid.id, "kind": kind, "kind_label": KINDS[kind][2], "label": label,
            "account_code": account.code, "counterpart": KINDS[kind][1], "trigger_on": on.isoformat(),
            "trigger_provisional": provisional, "acquired_cents": acquired, "paid_cents": paid, "amount_cents": amount,
            "posted": entry is not None, "posted_cents": _entry_amount(entry) if entry is not None else None,
            "entry": {"id": entry.id, "reference": entry.reference} if entry is not None else None,
            "dismissed": dismissed, "reason": decision.reason if decision is not None else None,
            "mixed": aid.nature == "mixed"})
    return {"items": items, "issues": issues}


def _decision(fy, aid_id: int) -> AidAccrual:
    row = AidAccrual.query.filter_by(aid_id=aid_id, fiscal_year_id=fy.id).first()
    if row is None:
        row = AidAccrual(aid_id=aid_id, fiscal_year_id=fy.id, status="posted")
        db.session.add(row)
    return row


def _reason(value) -> str | None:
    text = str(value or "").strip()
    return text[:500] or None


def post(fy, selection, user_id=None) -> list[JournalEntry]:
    """Passe les propositions choisies (`[{key, amount_cents?, reason?}]`) en écritures d'inventaire."""
    from app.services import closing

    if not isinstance(selection, list) or not selection:
        raise AidError("Sélectionnez au moins une aide.", "items")
    by_key = {p["key"]: p for p in proposals(fy)["items"]}
    entries = []
    for item in selection:
        proposal = by_key.get(item.get("key")) if isinstance(item, dict) else None
        if proposal is None:
            raise AidError("Proposition introuvable (déjà passée ou modifiée) : rechargez la page.", "items", 409)
        if proposal["posted"]:
            continue
        amount = item.get("amount_cents", proposal["amount_cents"])
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise AidError(f"{proposal['label']} : montant positif attendu.", "items")
        reason = _reason(item.get("reason"))
        if amount != proposal["amount_cents"] and (reason is None or len(reason) < MIN_REASON):
            raise AidError(f"{proposal['label']} : un montant différent du calcul demande un motif.", "items")
        inventory_kind, counterpart, title = KINDS[proposal["kind"]]
        entry = closing.add_inventory(fy, inventory_kind, proposal["account_code"], amount, f"{title} — {proposal['label']}",
                                      counterpart_code=counterpart, user_id=user_id, source_ref=proposal["key"])
        row = _decision(fy, proposal["aid_id"])
        row.kind, row.status, row.proposed_cents, row.amount_cents = proposal["kind"], "posted", proposal["amount_cents"], amount
        row.reason, row.journal_entry_id, row.user_id = reason, entry.id, user_id
        db.session.commit()
        entries.append(entry)
    return entries


def dismiss(fy, aid_id, reason, user_id=None) -> None:
    by_aid = {p["aid_id"]: p for p in proposals(fy)["items"]}
    proposal = by_aid.get(aid_id) if isinstance(aid_id, int) else None
    if proposal is None or proposal["posted"]:
        raise AidError("Proposition introuvable ou déjà passée.", "aid_id", 409)
    reason = _reason(reason)
    if reason is None or len(reason) < MIN_REASON:
        raise AidError("Motif obligatoire pour écarter une proposition (5 caractères au moins).", "reason")
    row = _decision(fy, aid_id)
    row.kind, row.status, row.proposed_cents, row.amount_cents = proposal["kind"], "dismissed", proposal["amount_cents"], None
    row.reason, row.journal_entry_id, row.user_id = reason, None, user_id
    db.session.flush()


def restore(fy, aid_id) -> None:
    row = AidAccrual.query.filter_by(aid_id=aid_id, fiscal_year_id=fy.id, status="dismissed").first()
    if row is None:
        raise AidError("Aucune proposition écartée pour ce dossier.", "aid_id", 404)
    db.session.delete(row)
    db.session.flush()


def checks(fy) -> list[tuple[str, str, int, str]]:
    """Contrôles de clôture : (clé, libellé, nombre, sévérité)."""
    if not enabled() or Aid.query.first() is None:
        return []
    data = proposals(fy)
    out = []
    pending = [p for p in data["items"] if p["kind"] == "accrued" and not p["posted"] and not p["dismissed"]]
    if pending:
        out.append(("aid_accrual", "Aides acquises sur l'exercice et non encore versées sans produit à recevoir (441) : "
                    "passez-les ou écartez-les depuis l'inventaire", len(pending), "anomaly"))
    deferred = [p for p in data["items"] if p["kind"] == "deferred" and not p["posted"] and not p["dismissed"]]
    if deferred:
        out.append(("aid_deferred", "Aides versées avant leur fait générateur (après la clôture) : produit constaté "
                    "d'avance (487) proposé à l'inventaire", len(deferred), "info"))
    if data["issues"]:
        out.append(("aid_issues", "Dossiers d'aide à compléter pour la clôture (décision, ventilation, trop-perçu)",
                    len(data["issues"]), "info"))
    from app.services import aid_grants
    from app.services.closing import _balances

    pending_releases = aid_grants.release_entry(fy) is None and any(r["amount_cents"] > 0 for r in aid_grants.releases(fy))
    if pending_releases:
        out.append(("aid_release", "Reprise des subventions d'investissement (139 / 747) de l'exercice non passée",
                    1, "info"))
    balance = sum(_balances(fy, ("441",)).values())
    accrued = sum(p["posted_cents"] or 0 for p in data["items"] if p["kind"] == "accrued" and p["posted"])
    expected = accrued + aid_grants.receivable_cents(fy)        # octrois de subventions d'investissement (AG3.d)
    if balance != expected:
        out.append(("aid_441", f"Solde du 441 ({balance / 100:.2f} €) différent des aides à recevoir passées et des "
                    f"octrois restant à percevoir ({expected / 100:.2f} €)".replace(".", ","), 1, "info"))
    return out
