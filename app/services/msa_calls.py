"""Registre des appels de cotisations MSA (lot AG7.c, claudedocs/design_msa.md § 5, AGD24).

- Appels saisis depuis l'avis d'appel ou le relevé de compte MSA, par exploitant et par année de cotisation : nature,
  exigibilité, montant, assiette indiquée, détail (cotisations, CSG déductible, CSG non déductible et CRDS, tiers).
- **Détail proposé** quand l'avis ne le donne pas : CSG et CRDS de l'année = taux × assiette retenue (historique AG7.b,
  selon l'option), réparties au prorata des appels saisis pour l'année ; marqué « estimé ».
- **Paiement** : débit bancaire rattaché à l'appel (débits de la MSA autour de l'exigibilité proposés).
- **Mensualisation** (profil agricole) : 11 mensualités de 1/11 des appels de l'année précédente (R.731-62 s.), à corriger.
- **Modulation** : rappel quand l'assiette retenue par Lyvre s'écarte de plus de 20 % de l'assiette de l'avis, demande
  au plus tard 15 jours avant l'exigibilité (R.731-60-1, D.731-17-1).
"""
from __future__ import annotations

from datetime import date, timedelta

from app.extensions import db
from app.models import BankTransaction, MsaBase, MsaCall, MsaPerson
from app.models.msa import MSA_CALL_KINDS
from app.services import reg_params
from app.services.msa import MsaError, person_name

SPLIT_FIELDS = ("contributions_cents", "csg_deductible_cents", "csg_crds_non_deductible_cents", "third_party_cents")
MODULATION_GAP_BP = 2000            # écart d'assiette signalé (20 %, à valider)
MODULATION_NOTICE_DAYS = 15         # demande au moins 15 jours avant l'exigibilité (D.731-17-1)
PAYMENT_WINDOW = (15, 30)           # débits de J-15 à J+30 de l'exigibilité
MONTHLY_DAY = 5                     # jour de prélèvement proposé, à corriger selon la caisse


# ------------------------------------------------------------------ outils

def _cents(value, field: str, allow_none: bool = True, allow_negative: bool = False) -> int | None:
    if value is None or value == "":
        if allow_none:
            return None
        raise MsaError("Montant obligatoire.", field)
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) > 10 ** 11 or (value < 0 and not allow_negative):
        raise MsaError("Montant en centimes attendu.", field)
    return value


def _day(value, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise MsaError("Date attendue (AAAA-MM-JJ).", field) from None


def _get(call_id: int) -> MsaCall:
    call = db.session.get(MsaCall, call_id)
    if call is None:
        raise MsaError("Appel introuvable.", status=404)
    return call


def retained_base(person: MsaPerson, year: int) -> tuple[int | None, str]:
    """Assiette des cotisations de `year` d'après l'historique : revenus year − 1 (option annuelle) ou moyenne des
    revenus year − 1 à year − 3."""
    bases = {r.year: r.base_cents for r in MsaBase.query.filter_by(person_id=person.id)}
    if person.base_option == "annual":
        value = bases.get(year - 1)
        return value, f"assiette annuelle (revenus {year - 1})"
    span = [year - 1, year - 2, year - 3]
    if any(y not in bases for y in span):
        return None, f"moyenne des revenus {year - 3} à {year - 1} incomplète"
    return round(sum(bases[y] for y in span) / 3), f"moyenne des revenus {year - 3} à {year - 1}"


# ------------------------------------------------------------------ détail proposé

def proposal(call: MsaCall) -> dict | None:
    """Détail estimé d'un appel sans détail : CSG / CRDS annuelles sur l'assiette retenue, au prorata des appels."""
    if any(getattr(call, f) is not None for f in SPLIT_FIELDS):
        return None
    base, label = retained_base(call.person, call.year)
    on = date(call.year, 12, 31)
    deductible_bp = reg_params.value("msa.csg.deductible_bp", on, None)
    non_deductible_bp = reg_params.value("msa.csg.non_deductible_bp", on, None)
    crds_bp = reg_params.value("msa.crds_bp", on, None)
    if base is None or base <= 0 or None in (deductible_bp, non_deductible_bp, crds_bp):
        return {"available": False, "reason": f"Assiette des cotisations {call.year} inconnue ({label}) : détail à saisir."}
    total = sum(c.amount_cents for c in MsaCall.query.filter_by(person_id=call.person_id, year=call.year)
                if c.kind != "regularization") or call.amount_cents
    deductible = round(base * deductible_bp / 10000 * call.amount_cents / total)
    non_deductible = round(base * (non_deductible_bp + crds_bp) / 10000 * call.amount_cents / total)
    contributions = call.amount_cents - deductible - non_deductible
    if contributions < 0:
        return {"available": False, "reason": "CSG et CRDS estimées supérieures aux appels saisis : saisissez tous les "
                                              "appels de l'année ou le détail de l'avis."}
    return {"available": True, "contributions_cents": contributions, "csg_deductible_cents": deductible,
            "csg_crds_non_deductible_cents": non_deductible, "third_party_cents": None,
            "basis": f"{label} : {base / 100:,.2f} €, au prorata des appels saisis pour {call.year}".replace(",", " ").replace(".", ",")}


def apply_proposal(call_id: int) -> MsaCall:
    call = _get(call_id)
    data = proposal(call)
    if not data or not data.get("available"):
        raise MsaError((data or {}).get("reason") or "Détail déjà saisi.")
    for field in SPLIT_FIELDS:
        setattr(call, field, data[field])
    call.estimated = True
    return call


# ------------------------------------------------------------------ saisie

def _apply(call: MsaCall, data: dict, creating: bool) -> None:
    if creating or "person_id" in data:
        person = db.session.get(MsaPerson, data.get("person_id")) if isinstance(data.get("person_id"), int) else None
        if person is None:
            raise MsaError("Exploitant introuvable.", "person_id")
        call.person_id = person.id
    if creating or "kind" in data:
        if data.get("kind") not in MSA_CALL_KINDS:
            raise MsaError("Nature d'appel inconnue.", "kind")
        call.kind = data["kind"]
    if creating or "due_on" in data:
        call.due_on = _day(data.get("due_on"), "due_on")
    if creating or "year" in data:
        year = data.get("year", call.due_on.year if creating else None)
        if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
            raise MsaError("Année de cotisation attendue.", "year")
        call.year = year
    if creating or "amount_cents" in data:
        call.amount_cents = _cents(data.get("amount_cents"), "amount_cents", allow_none=False,
                                   allow_negative=call.kind == "regularization")
    if "base_cents" in data:
        call.base_cents = _cents(data.get("base_cents"), "base_cents", allow_negative=True)
    touched = False
    for field in SPLIT_FIELDS:
        if field in data:
            setattr(call, field, _cents(data.get(field), field, allow_negative=call.kind == "regularization"))
            touched = True
    if touched:
        call.estimated = bool(data.get("estimated", False))
    parts = [getattr(call, f) for f in SPLIT_FIELDS]
    if any(p is not None for p in parts):
        if call.contributions_cents is None:
            call.contributions_cents = call.amount_cents - sum(p or 0 for p in parts[1:])
        if call.kind != "regularization" and call.contributions_cents < 0:
            raise MsaError("Détail supérieur au montant de l'appel.", "contributions_cents")
        if sum(getattr(call, f) or 0 for f in SPLIT_FIELDS) != call.amount_cents:
            raise MsaError("Le détail (cotisations, CSG, CRDS, tiers) doit égaler le montant de l'appel.", "contributions_cents")
    if "note" in data:
        call.note = str(data.get("note") or "").strip()[:300] or None


def create(data: dict) -> MsaCall:
    call = MsaCall()
    _apply(call, data, creating=True)
    db.session.add(call)
    return call


def update(call_id: int, data: dict) -> MsaCall:
    call = _get(call_id)
    _apply(call, data, creating=False)
    return call


def delete(call_id: int) -> None:
    call = _get(call_id)
    if call.journal_entry_id is not None:
        raise MsaError("Appel ventilé en comptabilité : supprimez d'abord l'écriture.", status=409)
    db.session.delete(call)


def monthly(person_id, year, day: int | None = None) -> list[MsaCall]:
    """11 mensualités de 1/11 des appels de l'année précédente (montant définitif inconnu), du 5 janvier au 5 novembre."""
    person = db.session.get(MsaPerson, person_id) if isinstance(person_id, int) else None
    if person is None:
        raise MsaError("Exploitant introuvable.", "person_id")
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        raise MsaError("Année de cotisation attendue.", "year")
    if MsaCall.query.filter_by(person_id=person.id, year=year, kind="monthly").first() is not None:
        raise MsaError(f"Mensualités {year} déjà saisies.", "year", 409)
    previous = sum(c.amount_cents for c in MsaCall.query.filter_by(person_id=person.id, year=year - 1))
    if previous <= 0:
        raise MsaError(f"Aucun appel {year - 1} saisi : mensualités à saisir depuis l'échéancier de la caisse.", "year")
    day = day if isinstance(day, int) and 1 <= day <= 28 else MONTHLY_DAY
    share = previous // 11
    calls = []
    for month in range(1, 12):
        amount = previous - share * 10 if month == 11 else share
        call = MsaCall(person_id=person.id, year=year, kind="monthly", due_on=date(year, month, day), amount_cents=amount,
                       estimated=True, note=f"1/11 des appels {year - 1} (R.731-62), à corriger d'après l'échéancier")
        db.session.add(call)
        calls.append(call)
    return calls


# ------------------------------------------------------------------ paiements

def _used_transactions(exclude: int | None = None) -> set[int]:
    rows = db.session.query(MsaCall.bank_transaction_id).filter(MsaCall.bank_transaction_id.isnot(None))
    if exclude is not None:
        rows = rows.filter(MsaCall.id != exclude)
    return {r[0] for r in rows}


def candidates(call_id: int) -> list[dict]:
    """Débits de J-15 à J+30 de l'exigibilité, non rattachés à un autre appel ; ceux de la MSA et du bon montant d'abord."""
    from app.services import agenda
    call = _get(call_id)
    used = _used_transactions(call.id)
    rows = BankTransaction.query.filter(
        BankTransaction.amount_cents < 0, BankTransaction.is_reversed.is_(False),
        BankTransaction.transaction_date.between(call.due_on - timedelta(days=PAYMENT_WINDOW[0]),
                                                 call.due_on + timedelta(days=PAYMENT_WINDOW[1])))
    out = []
    for tx in rows:
        if tx.id in used:
            continue
        payee = agenda.payee_matches(tx, "MSA")
        exact = -tx.amount_cents == call.amount_cents
        if payee or exact:
            out.append((not exact, not payee, abs((tx.transaction_date - call.due_on).days), tx, payee, exact))
    out.sort(key=lambda r: r[:3])
    return [agenda.transaction_payload(tx) | {"payee_matches": payee, "amount_matches": exact} for *_k, tx, payee, exact in out]


def link_payment(call_id: int, transaction_id) -> MsaCall:
    call = _get(call_id)
    if transaction_id is None:
        call.bank_transaction_id = None
        return call
    tx = db.session.get(BankTransaction, transaction_id) if isinstance(transaction_id, int) else None
    if tx is None or tx.amount_cents >= 0 or tx.is_reversed:
        raise MsaError("Débit bancaire introuvable.", "bank_transaction_id", 404)
    if tx.id in _used_transactions(call.id):
        raise MsaError("Ce débit est déjà rattaché à un autre appel.", "bank_transaction_id", 409)
    call.bank_transaction_id = tx.id
    return call


# ------------------------------------------------------------------ vue

def payload(call: MsaCall) -> dict:
    from app.services import agenda
    return {"id": call.id, "person_id": call.person_id, "year": call.year, "kind": call.kind,
            "kind_label": MSA_CALL_KINDS.get(call.kind, call.kind), "due_on": call.due_on.isoformat(),
            "amount_cents": call.amount_cents, "base_cents": call.base_cents,
            **{f: getattr(call, f) for f in SPLIT_FIELDS}, "estimated": call.estimated, "note": call.note,
            "journal_entry_id": call.journal_entry_id, "payment": agenda.transaction_payload(call.bank_transaction),
            "proposal": proposal(call)}


def _modulation(person: MsaPerson, calls: list[MsaCall], year: int, today: date) -> list[str]:
    base, label = retained_base(person, year)
    if base is None:
        return []
    out = []
    for call in calls:
        if call.base_cents is None or call.base_cents <= 0 or call.due_on <= today:
            continue
        if abs(base - call.base_cents) * 10000 > MODULATION_GAP_BP * call.base_cents:
            limit = call.due_on - timedelta(days=MODULATION_NOTICE_DAYS)
            if limit < today:
                continue
            out.append(f"{person_name(person)} : assiette de l'avis {call.base_cents / 100:,.0f} €, {label} "
                       f"{base / 100:,.0f} € ; modulation possible du {MSA_CALL_KINDS[call.kind].lower()} du "
                       f"{call.due_on:%d/%m/%Y}, à demander à la caisse au plus tard le {limit:%d/%m/%Y}."
                       .replace(",", " "))
            break
    return out


def listing(year: int, today: date | None = None) -> dict:
    from app.services import agri_profile
    today = today or date.today()
    people = []
    warnings = []
    for person in MsaPerson.query.order_by(MsaPerson.id):
        calls = (MsaCall.query.filter_by(person_id=person.id, year=year)
                 .order_by(MsaCall.due_on, MsaCall.id).all())
        totals = {"amount_cents": sum(c.amount_cents for c in calls),
                  "paid_cents": sum(c.amount_cents for c in calls if c.bank_transaction_id),
                  **{f: sum(getattr(c, f) or 0 for c in calls) for f in SPLIT_FIELDS},
                  "without_split": sum(1 for c in calls if all(getattr(c, f) is None for f in SPLIT_FIELDS))}
        base, label = retained_base(person, year)
        warnings += _modulation(person, calls, year, today)
        late = [c for c in calls if c.bank_transaction_id is None and c.due_on < today - timedelta(days=PAYMENT_WINDOW[1])]
        if late:
            warnings.append(f"{person_name(person)} : {len(late)} appel(s) échu(s) sans paiement rapproché.")
        people.append({"person": {"id": person.id, "name": person_name(person)}, "calls": [payload(c) for c in calls],
                       "totals": totals, "retained_base_cents": base, "retained_base_label": label})
    if not people:
        warnings.append("Aucun exploitant suivi : ouvrez l'onglet Assiette d'un exercice pour les créer.")
    return {"year": year, "people": people, "warnings": warnings,
            "monthly": bool(agri_profile.get().get("msa_monthly")),
            "kinds": [{"value": k, "label": v} for k, v in MSA_CALL_KINDS.items()]}
