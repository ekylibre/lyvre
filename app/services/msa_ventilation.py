"""Ventilation des cotisations MSA (lot AG7.d, claudedocs/design_msa.md § 6, AGD24).

- **EI** : les appels exigibles dans l'exercice sont des charges de l'exercice (646, engagement, Q-M7) :
  - ligne du résultat fiscal « CSG non déductible et CRDS » proposée depuis le registre (remplace la saisie d'AG6) ;
  - **charge à payer** à la clôture pour la part des appels de l'exercice non réglée au dernier jour
    (D 646 / C 4311, écriture d'inventaire extournée à l'ouverture) ;
  - contrôle : solde du 646 de l'exercice = total des appels de l'exercice.
- **Société** : les cotisations des associés exploitants sont débitées de leur compte courant 455 (Q-M2) : pas de
  charge, pas de ligne fiscale ; contrôle que les paiements rapprochés sont bien passés en 455 ; cotisations et CSG
  déductible de l'associé affichées pour la déduction sur sa quote-part (**à valider**).
"""
from __future__ import annotations

from app.extensions import db
from app.models import FiscalYear, JournalEntry, MsaCall, MsaPerson
from app.models.journal_entry import SOURCE_INVENTORY
from app.services.msa import MsaError, person_name

ACCRUAL_REF = "msa_accrual"
TOLERANCE_CENTS = 100


def _ei_person() -> MsaPerson | None:
    return MsaPerson.query.filter_by(associate_id=None).first()


def fy_calls(fy: FiscalYear, person: MsaPerson) -> list[MsaCall]:
    return (MsaCall.query.filter(MsaCall.person_id == person.id, MsaCall.due_on.between(fy.start_date, fy.end_date))
            .order_by(MsaCall.due_on, MsaCall.id).all())


# ------------------------------------------------------------------ résultat fiscal (EI)

def tax_lines(fy: FiscalYear) -> list[dict]:
    """Ligne « CSG non déductible et CRDS » des appels de l'exercice (EI seulement)."""
    person = _ei_person()
    if person is None:
        return []
    calls = fy_calls(fy, person)
    amount = sum(c.csg_crds_non_deductible_cents or 0 for c in calls)
    if not amount:
        return []
    estimated = any(c.estimated for c in calls)
    return [{"key": "msa_csg", "source": "msa", "amount_cents": amount, "link": f"/msa/?fiscal_year={fy.id}",
             "label": f"CSG non déductible et CRDS des appels MSA exigibles dans l'exercice ({len(calls)} appel(s))",
             "to_validate": estimated}]


def tax_warnings(fy: FiscalYear, lines: list[dict]) -> list[str]:
    out = []
    person = _ei_person()
    if person is None:
        return out
    missing = [c for c in fy_calls(fy, person) if c.csg_crds_non_deductible_cents is None]
    if missing:
        out.append(f"{len(missing)} appel(s) MSA de l'exercice sans détail de la CSG : ligne CSG non déductible incomplète "
                   "(Cotisations MSA › Appels, « Estimer » ou saisie de l'avis).")
    if any(l.get("source") == "msa" for l in lines) and any(l.get("kind") == "csg" for l in lines):
        out.append("CSG non déductible saisie à la main et reprise du registre des appels MSA : supprimez la ligne saisie.")
    return out


# ------------------------------------------------------------------ charge à payer (EI)

def accrual_entry(fy: FiscalYear) -> JournalEntry | None:
    return JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_INVENTORY, source_ref=ACCRUAL_REF).first()


def accrual(fy: FiscalYear) -> dict | None:
    """Part des appels de l'exercice non réglée au dernier jour (débit rapproché absent ou postérieur)."""
    person = _ei_person()
    if person is None:
        return None
    unpaid = [c for c in fy_calls(fy, person)
              if c.bank_transaction is None or c.bank_transaction.transaction_date > fy.end_date]
    entry = accrual_entry(fy)
    posted = sum(l.debit_cents for l in entry.lines) if entry is not None else None
    return {"amount_cents": sum(c.amount_cents for c in unpaid if c.amount_cents > 0),
            "calls": [{"id": c.id, "due_on": c.due_on.isoformat(), "amount_cents": c.amount_cents} for c in unpaid],
            "entry": {"id": entry.id, "reference": entry.reference, "amount_cents": posted} if entry is not None else None}


def post_accrual(fy: FiscalYear, user_id=None) -> JournalEntry:
    from app.services import closing
    data = accrual(fy)
    if data is None:
        raise MsaError("Charge à payer réservée à l'exploitant individuel (en société, cotisations en compte courant 455).")
    if data["entry"] is not None:
        raise MsaError("Charge à payer MSA déjà passée : supprimez-la pour la recalculer.", status=409)
    if data["amount_cents"] <= 0:
        raise MsaError("Aucun appel de l'exercice non réglé à la clôture.")
    try:
        return closing.add_inventory(fy, "accrued_expense", "646", data["amount_cents"],
                                     f"Cotisations MSA exigibles non réglées ({len(data['calls'])} appel(s))",
                                     counterpart_code="4311", user_id=user_id, source_ref=ACCRUAL_REF)
    except closing.ClosingError as exc:
        raise MsaError(exc.message, status=exc.status) from None


def delete_accrual(fy: FiscalYear, user_id=None) -> None:
    from app.services import closing
    entry = accrual_entry(fy)
    if entry is None:
        raise MsaError("Aucune charge à payer MSA.", status=404)
    try:
        closing.delete_inventory(fy, entry.id, user_id)
    except closing.ClosingError as exc:
        raise MsaError(exc.message, status=exc.status) from None


# ------------------------------------------------------------------ contrôles

def _booked_codes(tx) -> set[str]:
    from app.services import rule_entries
    if tx.journal_line is None:
        return set()
    entries = [tx.journal_line.entry]
    document = rule_entries.document_of(tx)
    if document is not None:
        entries.append(document)
    return {line.account.code for entry in entries for line in entry.lines
            if line.account is not None and not line.account.code.startswith("5")}


def _account_646(fy: FiscalYear) -> int:
    from app.services import closing
    return sum(closing._balances(fy, ("646",)).values())  # noqa: SLF001


def checks(fy: FiscalYear) -> list[tuple[str, str, int, str]]:
    from app.services import msa
    if not msa.enabled():
        return []
    found = []
    person = _ei_person()
    if person is not None:
        calls = fy_calls(fy, person)
        total = sum(c.amount_cents for c in calls)
        booked = _account_646(fy)
        if calls and abs(booked - total) > TOLERANCE_CENTS:
            found.append(("msa_646", f"Cotisations MSA : compte 646 {booked / 100:,.2f} € pour {total / 100:,.2f} € d'appels "
                          "exigibles dans l'exercice".replace(",", " ").replace(".", ","), 1, "info"))
        elif not calls and booked:
            found.append(("msa_register", "Cotisations MSA en 646 sans appel au registre (Cotisations MSA › Appels)", 1, "info"))
        data = accrual(fy)
        unpaid = data["amount_cents"] if data else 0
        if unpaid and data["entry"] is None:
            found.append(("msa_accrual", f"Appels MSA de l'exercice non réglés à la clôture ({unpaid / 100:,.2f} €) : charge à "
                          "payer à passer ou à écarter".replace(",", " ").replace(".", ","), 1, "anomaly"))
    else:
        wrong = 0
        for c in MsaCall.query.filter(MsaCall.due_on.between(fy.start_date, fy.end_date), MsaCall.bank_transaction_id.isnot(None)):
            codes = _booked_codes(c.bank_transaction)
            if codes and not any(code.startswith("455") for code in codes):
                wrong += 1
        if wrong:
            found.append(("msa_455", f"{wrong} paiement(s) de cotisations MSA d'associés non passés en compte courant 455",
                          wrong, "info"))
    return found


# ------------------------------------------------------------------ vue

def view(fy: FiscalYear) -> dict:
    from app.services import tax_result
    company_is = tax_result._is_company_is(fy)  # noqa: SLF001
    out = {"mode": "is" if company_is else "ei" if _ei_person() is not None else "company",
           "tax_lines": [] if company_is else tax_lines(fy), "accrual": None if company_is else accrual(fy),
           "checks": [{"key": k, "label": l, "severity": s} for k, l, _c, s in checks(fy)], "associates": []}
    if out["mode"] == "company":
        for person in MsaPerson.query.filter(MsaPerson.associate_id.isnot(None)).order_by(MsaPerson.id):
            calls = fy_calls(fy, person)
            out["associates"].append({
                "person_id": person.id, "name": person_name(person), "calls_cents": sum(c.amount_cents for c in calls),
                "deductible_cents": sum((c.contributions_cents or 0) + (c.csg_deductible_cents or 0) for c in calls),
                "non_deductible_cents": sum(c.csg_crds_non_deductible_cents or 0 for c in calls),
                "missing_split": sum(1 for c in calls if c.contributions_cents is None)})
    return out
