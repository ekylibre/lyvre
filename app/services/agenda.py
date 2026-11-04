"""Échéancier de l'exploitation (lot AG9a.b, claudedocs/design_echeancier_agricole.md § 5) : occurrences des fiches
applicables sur une fenêtre, statut de chacune, états enregistrés (faite, ignorée).

- Les fiches dont une condition porte sur une donnée non renseignée ne produisent pas d'occurrence : elles
  deviennent des **questions** (« Êtes-vous concerné ? »), à régler dans Structure › Activités et démarches.
- Les règles `lyvre` lisent le moteur de TVA : déclarations (CA3, CA12A), acomptes (3525 bis), demande 3520 ; leur
  statut vient de Lyvre (déposée → faite, validée → prête) et ne se coche pas à la main.
- Statut : faite, ignorée, prête, en retard, cette semaine (J à J+7), à préparer (J+8 à J+45), à venir.
- Paiements reconnus (lot AG9a.c, § 6.1) : un débit dont le libellé désigne l'organisme (`data/deadlines/payees.yml`),
  daté de J-10 à J+10 et égal à 5 % près au montant estimé, coche l'échéance de paiement (`origin = bank`). Détacher
  le paiement laisse un état `unlinked` : l'occurrence redevient à faire et n'est plus rapprochée automatiquement.
"""
from __future__ import annotations

from datetime import date, timedelta

from app.extensions import db
from app.models import BankTransaction, DeadlineState, FiscalYear, RfaClaim
from app.services import deadlines

WEEK_DAYS, PREPARE_DAYS = 7, 45
MATCH_DAYS, MATCH_TOLERANCE_BP, MATCH_LOOKBACK_DAYS = 10, 500, 90
STATUSES = {"done": "Faite", "skipped": "Ignorée", "ready": "Prête", "late": "En retard", "this_week": "Cette semaine",
            "to_prepare": "À préparer", "upcoming": "À venir"}


class AgendaError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def window(today: date) -> tuple[date, date]:
    return today - timedelta(days=90), today + timedelta(days=400)


def _timing(day: date, today: date) -> str:
    if day < today:
        return "late"
    if day <= today + timedelta(days=WEEK_DAYS):
        return "this_week"
    if day <= today + timedelta(days=PREPARE_DAYS):
        return "to_prepare"
    return "upcoming"


# ------------------------------------------------------------------ occurrences venues du moteur de TVA

def _lyvre(rule: dict, start: date, end: date, today: date) -> list[dict]:
    from app.services import vat_installments, vat_return

    source, out = rule["source"], []
    if source in ("vat_returns", "vat_installments"):
        for fy in FiscalYear.query.filter(FiscalYear.vat_period.isnot(None), FiscalYear.end_date >= start - timedelta(days=400),
                                          FiscalYear.start_date <= end).order_by(FiscalYear.start_date):
            for row in vat_return.periods(fy, today):
                annual = vat_return.kind_of(row["start"]) == vat_return.ANNUAL
                if source == "vat_returns":
                    if rule.get("form") == "CA12A" and not annual or rule.get("form") == "CA3" and annual:
                        continue
                    ret = row["return"]
                    out.append({"date": row["deadline"], "period": row["label"], "lyvre_status": ret.status if ret else None,
                                "amount_cents": ret.due_cents if ret is not None and ret.due_cents else None,
                                "link": f"/vat-returns/{row['period']}"})
                elif annual:
                    schedule = vat_installments.schedule((row["start"], row["end"]), today)
                    if schedule["dispensed"]:
                        continue
                    for item in schedule["items"]:
                        ret = item["return"]
                        amount = item["amount_cents"] if item["amount_cents"] is not None else schedule["proposed_cents"]
                        out.append({"date": item["deadline"], "period": f"acompte n° {item['number']} {schedule['label']}",
                                    "lyvre_status": ret.status if ret is not None else None, "amount_cents": amount,
                                    "amount_proposed": item["amount_cents"] is None, "link": "/vat-returns/"})
    elif source == "rfa":
        from app.models import JournalEntry
        first = db.session.query(db.func.min(JournalEntry.entry_date)).scalar()
        claims = {c.year: c for c in RfaClaim.query.all()}
        for year in range(max(start.year - 1, first.year if first else start.year - 1), end.year):
            claim = claims.get(year)
            out.append({"date": date(year + 1, 12, 31), "period": f"ventes {year}",
                        "lyvre_status": "declared" if claim is not None else None,
                        "amount_cents": claim.amount_cents if claim is not None else None, "link": f"/rfa/?year={year}"})
    elif source == "aids":
        # Lot AG3.c : date limite de la demande de paiement de chaque dossier ouvert (registre des aides).
        from app.models import Aid
        rows = Aid.query.filter(Aid.payment_request_deadline.isnot(None), Aid.status.notin_(("refused", "closed")),
                                Aid.payment_request_deadline.between(start, end))
        for aid in rows:
            out.append({"date": aid.payment_request_deadline, "period": f"{aid.label} {aid.campaign}",
                        "lyvre_status": "declared" if aid.payment_requested_on else None,
                        "link": f"/aids/?campaign={aid.campaign}"})
    seen, unique = set(), []
    for occ in out:  # une période civile peut être lue depuis deux exercices décalés
        key = (occ["date"], occ["period"])
        if key not in seen and start <= occ["date"] <= end:
            seen.add(key)
            unique.append(occ)
    return unique


# ------------------------------------------------------------------ calcul

def occurrences(start: date, end: date, today: date | None = None, ctx: deadlines.Context | None = None) -> dict:
    """{items, questions} : occurrences des fiches applicables entre `start` et `end`, et fiches à préciser."""
    today = today or date.today()
    ctx = ctx or deadlines.context()
    states = {(s.deadline_id, s.occurs_on, s.period): s for s in
              DeadlineState.query.filter(DeadlineState.occurs_on.between(start, end))}
    items, questions = [], []
    for fiche in deadlines.fiches():
        fiche_applies = deadlines.applies(fiche.get("applies"), ctx, today)
        if fiche_applies is None:
            questions.append(fiche["id"])
            continue
        for index, event in enumerate(fiche.get("events") or [], start=1):
            rule = event["rule"]
            if rule["type"] == "lyvre":
                found = _lyvre(rule, start, end, today)
            else:
                found = [{"date": o.date, "period": f"{o.period} · {o.note}" if rule["type"] == "leases" else o.period,
                          "to_confirm": o.to_confirm, "note": o.note if rule["type"] != "leases" else None,
                          "edi_date": o.edi_date} for o in deadlines.dates(rule, start, end, ctx)]
            for occ in found:
                if deadlines.applies(fiche.get("applies"), ctx, occ["date"]) is False:
                    continue  # régime changé à la date de l'occurrence
                event_applies = deadlines.applies(event.get("applies"), ctx, occ["date"])
                if event_applies is False:
                    continue
                if event_applies is None:
                    if fiche["id"] not in questions:
                        questions.append(fiche["id"])
                    continue
                deadline_id = f"{fiche['id']}#{index}"
                state = states.get((deadline_id, occ["date"], occ["period"]))
                unlinked = state is not None and state.status == "unlinked"
                if unlinked:
                    state = None
                lyvre_status = occ.get("lyvre_status")
                if state is not None:
                    status = state.status
                elif lyvre_status in ("declared", "refunded"):
                    status = "done"
                elif lyvre_status == "validated":
                    status = "ready"
                else:
                    status = _timing(occ["date"], today)
                reminders = event.get("reminders") or list(deadlines.DEFAULT_REMINDERS)
                reliability = event.get("reliability") or fiche["reliability"]
                items.append({
                    "key": f"{deadline_id}|{occ['date'].isoformat()}|{occ['period']}", "deadline_id": deadline_id,
                    "fiche_id": fiche["id"], "label": event["label"], "title": fiche["title"], "domain": fiche["domain"],
                    "organism": fiche["organism"], "date": occ["date"], "period": occ["period"], "status": status,
                    "timing": _timing(occ["date"], today), "to_confirm": bool(occ.get("to_confirm")) or reliability == "I",
                    "note": occ.get("note"), "edi_date": occ.get("edi_date"), "amount_cents": occ.get("amount_cents"),
                    "amount_proposed": bool(occ.get("amount_proposed")), "managed": rule["type"] == "lyvre",
                    "link": occ.get("link"), "action": event.get("action"), "quiet": bool(event.get("quiet")),
                    "reminder_only": bool(fiche.get("reminder_only")), "reliability": reliability,
                    "reminder_from": occ["date"] - timedelta(days=max(reminders)), "state": state_payload(state),
                    "payment": bool(event.get("payment")), "unlinked": unlinked})
    items.sort(key=lambda i: (i["date"], i["fiche_id"], i["period"]))
    return {"items": items, "questions": questions}


def transaction_payload(tx: BankTransaction | None) -> dict | None:
    if tx is None:
        return None
    return {"id": tx.id, "bank_account_id": tx.bank_account_id, "date": tx.transaction_date.isoformat(),
            "label": tx.label or tx.counterparty or "", "amount_cents": tx.amount_cents}


def state_payload(state: DeadlineState | None) -> dict | None:
    if state is None:
        return None
    return {"id": state.id, "status": state.status, "done_on": state.done_on.isoformat() if state.done_on else None,
            "origin": state.origin, "bank_transaction_id": state.bank_transaction_id, "note": state.note,
            "transaction": transaction_payload(state.bank_transaction)}


# ------------------------------------------------------------------ états

def find_occurrence(deadline_id: str, occurs_on: date, period: str, today: date) -> dict:
    found = occurrences(occurs_on, occurs_on, today)["items"]
    occ = next((i for i in found if i["deadline_id"] == deadline_id and i["period"] == period), None)
    if occ is None:
        raise AgendaError("Échéance introuvable à cette date.", "deadline_id", status=404)
    return occ


def set_state(deadline_id: str, occurs_on: date, period: str, status: str, done_on: date | None = None,
              note: str | None = None, user_id=None, today: date | None = None, origin: str = "manual",
              bank_transaction_id: int | None = None) -> DeadlineState:
    """Marque une occurrence faite ou ignorée (sans commit). Les échéances gérées par Lyvre (déclarations de TVA,
    3520) suivent leur déclaration et ne se marquent pas à la main, sauf par le rattachement d'un paiement
    (`bank_transaction_id`, échéances de paiement seulement)."""
    if status not in ("done", "skipped"):
        raise AgendaError("Statut : faite ou ignorée.", "status")
    occ = find_occurrence(deadline_id, occurs_on, period, today or date.today())
    tx = None
    if bank_transaction_id is not None:
        if not occ["payment"] or status != "done":
            raise AgendaError("Seule une échéance de paiement se rattache à un paiement.", "bank_transaction_id")
        tx = db.session.get(BankTransaction, bank_transaction_id)
        if tx is None or tx.amount_cents >= 0 or tx.is_reversed:
            raise AgendaError("Débit bancaire introuvable.", "bank_transaction_id", status=404)
        if DeadlineState.query.filter_by(bank_transaction_id=tx.id, status="done").first() is not None:
            raise AgendaError("Ce paiement est déjà rattaché à une autre échéance.", "bank_transaction_id", status=409)
        origin, done_on = "bank", tx.transaction_date
    elif occ["managed"]:
        raise AgendaError("Échéance suivie par Lyvre : elle passe à « faite » au dépôt de la déclaration.", status=409)
    if occ["state"] is not None:
        raise AgendaError("Échéance déjà marquée.", status=409)
    note = (str(note or "").strip())[:300] or None
    if status == "skipped" and not note:
        raise AgendaError("Indiquez pourquoi l'échéance ne vous concerne pas.", "note")
    state = DeadlineState.query.filter_by(deadline_id=deadline_id, occurs_on=occurs_on, period=period).first()
    if state is None:  # sinon : paiement détaché, réutilisé
        state = DeadlineState(deadline_id=deadline_id, occurs_on=occurs_on, period=period)
        db.session.add(state)
    state.status, state.origin, state.note, state.user_id = status, origin, note, user_id
    state.done_on = (done_on or date.today()) if status == "done" else None
    state.bank_transaction_id = tx.id if tx is not None else None
    db.session.flush()
    return state


def clear_state(state: DeadlineState) -> None:
    """Remet l'occurrence à faire. Un paiement reconnu devient « détaché » pour ne pas être rapproché à nouveau."""
    if state.origin == "bank":
        state.status, state.done_on = "unlinked", None
    else:
        db.session.delete(state)
    db.session.flush()


# ------------------------------------------------------------------ paiements reconnus (lot AG9a.c)

def _text(tx: BankTransaction) -> str:
    return f" {deadlines.normalize(tx.label)} {deadlines.normalize(tx.counterparty)} "


def payee_matches(tx: BankTransaction, organism: str) -> bool:
    """Le libellé ou la contrepartie du débit contient un motif d'un des organismes de la fiche (« DDT(M), ASP »)."""
    table = deadlines.payees()
    patterns = [p for name in (part.strip() for part in organism.split(",")) for p in table.get(name, ())]
    text = _text(tx)
    return any(f" {p} " in text for p in patterns)


def amount_matches(tx: BankTransaction, amount_cents: int | None) -> bool:
    if not amount_cents:
        return True
    return abs(-tx.amount_cents - amount_cents) * 10000 <= MATCH_TOLERANCE_BP * amount_cents


def _debits(start: date, end: date) -> list[BankTransaction]:
    used = {row[0] for row in db.session.query(DeadlineState.bank_transaction_id)
            .filter(DeadlineState.status == "done", DeadlineState.bank_transaction_id.isnot(None))}
    return [tx for tx in BankTransaction.query.filter(
        BankTransaction.amount_cents < 0, BankTransaction.is_reversed.is_(False),
        BankTransaction.transaction_date.between(start, end)).order_by(BankTransaction.transaction_date, BankTransaction.id)
        if tx.id not in used]


def _open_payment(item: dict) -> bool:
    return item["payment"] and item["state"] is None and not item["unlinked"] and item["status"] not in ("done", "skipped")


def candidates(item: dict) -> list[dict]:
    """Débits de l'organisme à J-10/J+10 de l'échéance, non rattachés, quel que soit leur montant (rattachement à la
    main), les plus proches d'abord."""
    days = timedelta(days=MATCH_DAYS)
    found = [tx for tx in _debits(item["date"] - days, item["date"] + days) if payee_matches(tx, item["organism"])]
    found.sort(key=lambda tx: (not amount_matches(tx, item["amount_cents"]), abs((tx.transaction_date - item["date"]).days)))
    return [transaction_payload(tx) | {"amount_matches": bool(item["amount_cents"]) and amount_matches(tx, item["amount_cents"])}
            for tx in found]


def match_payments(today: date | None = None, ctx: deadlines.Context | None = None) -> list[DeadlineState]:
    """Rattache les débits reconnus aux échéances de paiement ouvertes de J-90 à J+10 (sans commit). Chaque débit et
    chaque échéance ne servent qu'une fois : le montant égal d'abord, puis la date la plus proche."""
    today = today or date.today()
    days = timedelta(days=MATCH_DAYS)
    items = [i for i in occurrences(today - timedelta(days=MATCH_LOOKBACK_DAYS), today + days, today, ctx)["items"]
             if _open_payment(i)]
    if not items:
        return []
    debits = _debits(min(i["date"] for i in items) - days, max(i["date"] for i in items) + days)
    pairs = []
    for item in items:
        for tx in debits:
            gap = abs((tx.transaction_date - item["date"]).days)
            if gap <= MATCH_DAYS and payee_matches(tx, item["organism"]) and amount_matches(tx, item["amount_cents"]):
                diff = abs(-tx.amount_cents - item["amount_cents"]) if item["amount_cents"] else None
                pairs.append(((diff is None, diff or 0, gap, tx.id), item, tx))
    pairs.sort(key=lambda p: p[0])
    taken_items, taken_tx, created = set(), set(), []
    for _, item, tx in pairs:
        if item["key"] in taken_items or tx.id in taken_tx:
            continue
        taken_items.add(item["key"])
        taken_tx.add(tx.id)
        state = DeadlineState(deadline_id=item["deadline_id"], occurs_on=item["date"], period=item["period"],
                              status="done", done_on=tx.transaction_date, origin="bank", bank_transaction_id=tx.id)
        db.session.add(state)
        created.append(state)
    db.session.flush()
    return created


def fiche_payload(fiche: dict) -> dict:
    keys = ("id", "title", "domain", "organism", "summary", "prepare", "lyvre_data", "penalties", "links", "reliability",
            "reminder_only")
    return {k: fiche.get(k) for k in keys} | {"domain_label": deadlines.DOMAINS[fiche["domain"]]}
