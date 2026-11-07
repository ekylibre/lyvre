"""Assiette sociale MSA des non-salariés agricoles (lot AG7.a, claudedocs/design_msa.md § 3, AGD24).

Pour l'exercice clos dans l'année N (revenus N, cotisations N+1 en assiette annuelle) et par exploitant :
1. résultat fiscal BA de l'exploitant (AG6 : quote-part, après JA et DEP) ;
2. réintégrations (CSS R.136-2) : abattement JA (73 B), stock bloqué (72 B bis), à-valoir social (72 F, saisi) ;
   en EI, cotisations personnelles 646 moins la CSG / CRDS non déductible déjà réintégrée au fiscal ; en société,
   les cotisations des associés passent par leur compte courant 455 et ne sont pas des charges (Q-M2) ;
3. déduction de la DJA comprise dans le résultat (part d'exploitation de l'exercice de la décision, reprises 139),
   répartie comme le résultat (Q-M4) ;
4. DEP, 73 A, 75-0 A, 75-0 D, plus-values à long terme et à court terme exonérées : laissés tels qu'au fiscal ;
5. abattement de 26 % dont le **montant** est borné entre 1,76 % et 130 % du PASS ; le plancher s'applique aussi à un
   revenu nul ou déficitaire (Q-M3).
Figé dans `msa_bases` (source « lyvre ») à la clôture définitive de l'exercice.
"""
from __future__ import annotations

import json
from datetime import date

from app.extensions import db
from app.models import FiscalYear, MsaAdjustment, MsaBase, MsaPerson
from app.models.msa import MSA_ADJUSTMENT_KINDS, MSA_BASE_OPTIONS, MSA_STATUSES
from app.services import reg_params

REFORM_FIRST_YEAR = 2025          # revenus 2025 → cotisations 2026 (LFSS 2024 art. 18 VII)


class MsaError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def enabled() -> bool:
    from app.services import tax_result
    return tax_result.enabled()


def _p(key: str, on: date):
    return reg_params.value(key, on, None)


def _pass(year: int) -> tuple[int | None, str | None]:
    """PASS de l'année de cotisation (revenus N → cotisations N+1), sinon le dernier connu."""
    value = _p("msa.pass_cents", date(year + 1, 1, 1))
    if value is not None:
        return value, None
    history = sorted(reg_params.history("msa.pass_cents"), key=lambda p: p.valid_from)
    if not history:
        return None, "PASS non paramétré (msa.pass_cents)."
    last = history[-1]
    return last.value, f"PASS {year + 1} non paramétré : PASS {last.valid_from.year} retenu pour les bornes de l'abattement."


def abatement(income: int, year: int) -> dict:
    """Abattement de 26 % borné (montant entre le plancher et le plafond) ; plancher si revenu nul ou déficitaire."""
    on = date(year, 12, 31)
    rate, floor_bp, ceiling_bp = (_p(k, on) for k in ("msa.base.abatement_rate_bp", "msa.base.abatement_floor_pass_bp",
                                                       "msa.base.abatement_ceiling_pass_bp"))
    pass_cents, warning = _pass(year)
    if None in (rate, floor_bp, ceiling_bp, pass_cents):
        return {"error": warning or "Paramètres de l'abattement MSA absents (msa.base.*)."}
    floor = round(pass_cents * floor_bp / 10000)
    ceiling = round(pass_cents * ceiling_bp / 10000)
    raw = round(income * rate / 10000) if income > 0 else 0
    amount = min(max(raw, floor), ceiling)
    bound = "plancher" if amount == floor and raw < floor else "plafond" if amount == ceiling and raw > ceiling else None
    return {"amount_cents": amount, "raw_cents": raw, "floor_cents": floor, "ceiling_cents": ceiling,
            "rate_bp": rate, "pass_cents": pass_cents, "bound": bound, "warning": warning}


# ------------------------------------------------------------------ exploitants

def people(fy: FiscalYear, rows: list[dict] | None = None) -> tuple[list[tuple[MsaPerson, dict | None]], list[str]]:
    """Exploitants suivis à la clôture : (personne, quote-part ou None en EI). Crée les fiches manquantes.
    `rows` : associés du résultat fiscal (quote-part, résultat et JA de chacun), sinon `tax_result.shares`."""
    from app.services import organization, tax_result
    warnings: list[str] = []
    if rows is None:
        rows, warnings = tax_result.shares(fy)
    out = []
    if rows:
        for row in rows:
            if not row["is_operator"]:
                continue
            person = MsaPerson.query.filter_by(associate_id=row["associate_id"]).first()
            if person is None:
                person = MsaPerson(associate_id=row["associate_id"])
                db.session.add(person)
            out.append((person, row))
        others = [r["name"] for r in rows if not r["is_operator"]]
        if others:
            warnings.append(f"Associés non exploitants, sans assiette NSA : {', '.join(others)}.")
        if not out:
            warnings.append("Aucun associé exploitant : cochez « exploitant » sur la fiche des associés concernés.")
    elif (organization.get().legal_form_code or "EI") == "EI":
        person = MsaPerson.query.filter_by(associate_id=None).first()
        if person is None:
            person = MsaPerson()
            db.session.add(person)
        out.append((person, None))
    else:
        warnings.append("Société sans associés saisis : assiette par associé impossible (Structure › Associés).")
    db.session.flush()
    return out, warnings


def person_name(person: MsaPerson) -> str:
    if person.associate_id:
        return person.associate.name
    from app.services import organization
    return f"Exploitant ({organization.get().name})"


def person_payload(person: MsaPerson) -> dict:
    return {"id": person.id, "associate_id": person.associate_id, "name": person_name(person), "status": person.status,
            "status_label": MSA_STATUSES.get(person.status, person.status), "base_option": person.base_option,
            "base_option_label": MSA_BASE_OPTIONS.get(person.base_option, person.base_option),
            "option_since": person.option_since.isoformat() if person.option_since else None,
            "atexa_category": person.atexa_category, "note": person.note}


# ------------------------------------------------------------------ éléments de l'exploitation

def _blocked_stock(fy: FiscalYear) -> int:
    """Déduction du stock bloqué (72 B bis) comprise dans l'écart de stocks : à réintégrer (positif)."""
    from app.services import stock_tax
    return -sum(g["gap_cents"] for g in stock_tax.totals(fy)["gaps"] if g["fiscal_method"] == "frozen")


def _dja(fy: FiscalYear) -> tuple[int, list[str]]:
    """DJA comprise dans le résultat de l'exercice : part d'exploitation (exercice de la décision) et reprises 139."""
    from app.models import Aid
    from app.services import aid_grants, aids

    total, labels = 0, []
    dja_ids = set()
    for aid in Aid.query.filter_by(scheme="dja").filter(Aid.status != "refused"):
        dja_ids.add(aid.id)
        if aid.decision_on and fy.start_date <= aid.decision_on <= fy.end_date:
            acquired = aids.acquired_cents(aid)
            if aid.nature == "operating":
                part = acquired
            elif aid.nature == "mixed" and aid.investment_share_cents is not None:
                part = max(acquired - aid.investment_share_cents, 0)
            else:
                part = 0
            if part:
                total += part
                labels.append(f"part d'exploitation {aid.campaign}")
    if dja_ids and aid_grants.enabled():
        released = sum(r["amount_cents"] for r in aid_grants.releases(fy) if r["aid_id"] in dja_ids)
        if released:
            total += released
            labels.append("reprise de la subvention d'investissement")
    return total, labels


def _contributions_646(fy: FiscalYear) -> int:
    from app.services import closing
    return sum(closing._balances(fy, ("646",)).values())  # noqa: SLF001


def _split(amount: int, share_bp: int) -> int:
    return round(amount * share_bp / 10000)


# ------------------------------------------------------------------ calcul

def compute(fy: FiscalYear) -> dict:
    from app.services import tax_result

    head = {"fiscal_year": {"id": fy.id, "label": fy.label, "end_date": fy.end_date.isoformat(), "status": fy.status},
            "year": fy.end_date.year, "people": [], "warnings": [], "reason": None}
    if tax_result._is_company_is(fy):  # noqa: SLF001
        head["reason"] = ("Société à l'IS : l'assiette des dirigeants non salariés est leur rémunération et la part des "
                          "dividendes au-delà de 10 % du capital, hors bénéfices agricoles.")
        return head
    year = fy.end_date.year
    from app.services import tax_profile
    if tax_profile.current_value("ba_regime", fy.end_date) == "micro":   # lot CG3.c (MS3)
        head["reason"] = ("Micro-BA : l'assiette sociale est la moyenne des recettes hors taxes des 3 années précédentes "
                          "(ou celles de N-1 sur option) après l'abattement de 87 % du micro-BA, et non le résultat "
                          "comptable ; Lyvre ne la calcule pas. Saisissez l'assiette de l'avis MSA dans l'historique.")
        return head
    if year < REFORM_FIRST_YEAR:
        head["reason"] = (f"Revenus {year} : ancienne assiette (avant la réforme de 2026), reconstituée par la caisse. "
                          "Saisissez l'assiette de l'avis MSA dans l'historique.")
        return head
    tr = tax_result.view(fy)
    pairs, warnings = people(fy, tr["associates"])
    blocked = _blocked_stock(fy)
    dja, dja_labels = _dja(fy)
    company = any(row is not None for _p_, row in pairs)
    csg_tax = sum(l["amount_cents"] for l in tr["lines"]
                  if (l.get("source") == "manual" and l.get("kind") == "csg") or l.get("source") == "msa")
    contributions = 0 if company else _contributions_646(fy)
    adjustments = {}
    for adj in MsaAdjustment.query.filter_by(fiscal_year_id=fy.id).order_by(MsaAdjustment.id):
        adjustments.setdefault(adj.person_id, []).append(adj)
    out = []
    for person, row in pairs:
        lines = []
        if row is None:
            fiscal = tr["fiscal_result_cents"]
            ja = -sum(l["amount_cents"] for l in tr["lines"] if l.get("source") == "young_farmer")
            share = 10000
        else:
            fiscal = row.get("fiscal_result_cents", 0)
            ja = row.get("ja_cents", 0)
            share = row["share_bp"]
        if ja:
            lines.append({"key": "ja", "label": "Abattement jeune agriculteur (73 B) réintégré", "amount_cents": ja,
                          "basis": "CSS R.136-2"})
        if blocked:
            lines.append({"key": "blocked_stock", "label": "Stock à rotation lente bloqué (72 B bis) réintégré",
                          "amount_cents": _split(blocked, share), "basis": "CSS R.136-2"})
        if contributions:
            net = contributions - csg_tax
            lines.append({"key": "contributions", "label": "Cotisations sociales personnelles (646), hors CSG / CRDS non "
                          "déductible déjà réintégrée", "amount_cents": net, "basis": "assiette hors cotisations sociales",
                          "detail": {"account_646_cents": contributions, "csg_tax_line_cents": csg_tax}})
        if dja:
            lines.append({"key": "dja", "label": f"DJA comprise dans le résultat ({', '.join(dja_labels)})",
                          "amount_cents": -_split(dja, share), "basis": "CSS L.136-4 I A 1°"})
        for adj in adjustments.get(person.id, []):
            sign = -1 if adj.kind == "deduct" else 1
            lines.append({"key": f"adj_{adj.id}", "id": adj.id, "kind": adj.kind, "label": MSA_ADJUSTMENT_KINDS[adj.kind],
                          "amount_cents": sign * adj.amount_cents, "reason": adj.reason, "basis": "saisie"})
        income = fiscal + sum(l["amount_cents"] for l in lines)
        abat = abatement(income, year)
        if abat.get("error"):
            warnings.append(abat["error"])
            base = None
        else:
            base = income - abat["amount_cents"]
            if abat.get("warning") and abat["warning"] not in warnings:
                warnings.append(abat["warning"])
        out.append({"person": person_payload(person), "share_bp": share, "fiscal_result_cents": fiscal, "lines": lines,
                    "income_cents": income, "abatement": abat, "base_cents": base})
    if company and any(p["fiscal_result_cents"] for p in out):
        warnings.append("Société : cotisations des associés débitées de leur compte courant 455, sans effet sur "
                        "l'assiette ; leur déduction sur la quote-part de chacun est à valider (AGD24).")
    warnings.append("Option de déduction de la rente du sol (D.731-24 CRPM) : demande ou dénonciation à la caisse avant "
                    "le 30 juin, non calculée par Lyvre.")
    head.update(people=out, warnings=warnings, tax_frozen=tr["frozen"])
    return head


def view(fy: FiscalYear) -> dict:
    """Assiette de l'exercice ; enregistrée dans l'historique (source « lyvre ») une fois le résultat fiscal figé."""
    data = compute(fy)
    if data.get("tax_frozen"):
        for item in data["people"]:
            if item["base_cents"] is None:
                continue
            row = MsaBase.query.filter_by(person_id=item["person"]["id"], year=data["year"]).first()
            if row is not None and row.source == "entered":
                continue
            if row is None:
                row = MsaBase(person_id=item["person"]["id"], year=data["year"], source="lyvre")
                db.session.add(row)
            row.income_cents, row.abatement_cents = item["income_cents"], item["abatement"]["amount_cents"]
            row.base_cents = item["base_cents"]
            row.detail_json = json.dumps({"fiscal_year_id": fy.id, "lines": item["lines"]})
    db.session.flush()
    for item in data["people"]:
        person = db.session.get(MsaPerson, item["person"]["id"])
        item["history"] = history(person)
        item["comparison"] = comparison(person, data["year"], item["base_cents"], current_income=item["income_cents"])
        from app.services import msa_estimate                     # lot AG7.e : estimation indicative
        item["estimate"] = msa_estimate.estimate(item["comparison"]["retained_cents"],
                                                 item["comparison"]["contribution_year"], person.status,
                                                 person.atexa_category)
    db.session.commit()
    return data


# ------------------------------------------------------------------ historique et option (AG7.b)

def base_payload(row: MsaBase) -> dict:
    return {"id": row.id, "year": row.year, "source": row.source, "income_cents": row.income_cents,
            "abatement_cents": row.abatement_cents, "base_cents": row.base_cents, "note": row.note}


def history(person: MsaPerson) -> list[dict]:
    rows = MsaBase.query.filter_by(person_id=person.id).order_by(MsaBase.year.desc())
    return [base_payload(r) for r in rows]


def comparison(person: MsaPerson, year: int, current_base: int | None, today: date | None = None,
               current_income: int | None = None) -> dict:
    """Assiette des cotisations de l'année C = year + 1 : annuelle (revenus de `year`) ou moyenne triennale
    (revenus de year, year − 1, year − 2) ; état de l'option de l'exploitant et délais (L.731-15, D.731-26)."""
    today = today or date.today()
    rows = MsaBase.query.filter_by(person_id=person.id).all()
    bases = {r.year: r.base_cents for r in rows}
    incomes = {r.year: r.income_cents for r in rows}
    if current_base is not None:
        bases[year] = current_base
    if current_income is not None:
        incomes[year] = current_income
    contribution_year = year + 1
    span = [year, year - 1, year - 2]
    missing = [y for y in span if y not in bases]
    annual = bases.get(year)
    notes = []
    triennial = None
    if not missing:
        # Lot CG3.c (Q4) : moyenne des revenus des 3 années, puis abattement de 26 % borné sur cette moyenne. Une année
        # sans revenu connu (assiette saisie depuis l'avis seule) : moyenne des assiettes, comme avant.
        if all(incomes.get(y) is not None for y in span):
            average = round(sum(incomes[y] for y in span) / 3)
            abat = abatement(average, year)
            triennial = None if abat.get("error") else average - abat["amount_cents"]
        if triennial is None:
            triennial = round(sum(bases[y] for y in span) / 3)
            unknown = [str(y) for y in span if incomes.get(y) is None]
            if unknown:
                notes.append(f"Revenu {', '.join(unknown)} inconnu (assiette seule) : moyenne triennale des assiettes. "
                             "Saisissez le revenu avant abattement pour appliquer l'abattement à la moyenne.")
    old = [y for y in span if y < REFORM_FIRST_YEAR]
    if old:
        notes.append(f"Revenus {', '.join(map(str, sorted(old)))} : assiette reconstituée par la caisse (ancienne assiette "
                     "« super brute », puis abattement de 26 %) ; saisissez le montant de l'avis MSA.")
    best = diff = None
    if annual is not None and triennial is not None:
        diff = annual - triennial
        best = "annual" if diff < 0 else "triennial" if diff > 0 else None
    option = {"current": person.base_option, "since": person.option_since.isoformat() if person.option_since else None}
    if person.base_option == "annual":
        start = person.option_since.year if person.option_since else None
        option["commitment_end"] = f"{start + 4}-12-31" if start else None
        option["deadline"] = f"{today.year}-11-30"
        option["deadline_label"] = (f"Dénonciation au plus tard le 30/11/{today.year} pour revenir à la moyenne triennale au "
                                    f"01/01/{today.year + 1} ; pas de nouvelle option pendant 6 ans ensuite.")
        retained = annual
    else:
        option["deadline"] = f"{contribution_year}-06-30"
        option["deadline_label"] = (f"Option pour l'assiette annuelle des cotisations {contribution_year} à demander à la caisse "
                                    f"au plus tard le 30/06/{contribution_year}, pour 5 ans reconduits tacitement.")
        retained = triennial
    if contribution_year in (2027, 2028):
        notes.append(f"Expérimentation (LFSS 2026 art. 16) : cotisations {contribution_year} calculables sur l'estimation des "
                     f"revenus {contribution_year}, demande du 01/10/{contribution_year - 1} au 31/03/{contribution_year}, "
                     "irrévocable pour l'année, régularisée ensuite.")
    return {"contribution_year": contribution_year, "span": span, "bases": {str(y): bases.get(y) for y in span},
            "missing": missing, "annual_cents": annual, "triennial_cents": triennial, "difference_cents": diff,
            "best": best, "retained_cents": retained, "option": option, "notes": notes}


def save_base(person_id: int, year, data: dict) -> MsaBase:
    person = _person(person_id)
    if isinstance(year, bool) or not isinstance(year, int) or not 2000 <= year <= 2100:
        raise MsaError("Année attendue.", "year")
    row = MsaBase.query.filter_by(person_id=person.id, year=year).first()
    if row is not None and row.source == "lyvre":
        raise MsaError("Assiette calculée par Lyvre à la clôture : elle ne se saisit pas.", "year", 409)
    values = {}
    for field, required in (("base_cents", True), ("income_cents", False), ("abatement_cents", False)):
        value = data.get(field)
        if value is None and not required:
            values[field] = None
            continue
        if isinstance(value, bool) or not isinstance(value, int) or abs(value) > 10 ** 11:
            raise MsaError("Montant en centimes attendu.", field)
        values[field] = value
    if row is None:
        row = MsaBase(person_id=person.id, year=year, source="entered")
        db.session.add(row)
    row.base_cents, row.income_cents, row.abatement_cents = values["base_cents"], values["income_cents"], values["abatement_cents"]
    row.note = str(data.get("note") or "").strip()[:300] or None
    return row


def delete_base(person_id: int, year: int) -> None:
    person = _person(person_id)
    row = MsaBase.query.filter_by(person_id=person.id, year=year).first()
    if row is None:
        raise MsaError("Assiette introuvable.", status=404)
    if row.source == "lyvre":
        raise MsaError("Assiette calculée par Lyvre à la clôture : elle ne se supprime pas.", status=409)
    db.session.delete(row)


def meta() -> dict:
    options = lambda d: [{"value": k, "label": v} for k, v in d.items()]  # noqa: E731
    return {"statuses": options(MSA_STATUSES), "base_options": options(MSA_BASE_OPTIONS),
            "adjustment_kinds": options(MSA_ADJUSTMENT_KINDS)}


# ------------------------------------------------------------------ saisie

def _person(person_id) -> MsaPerson:
    person = db.session.get(MsaPerson, person_id) if isinstance(person_id, int) else None
    if person is None:
        raise MsaError("Exploitant introuvable.", "person_id", 404)
    return person


def add_adjustment(fy: FiscalYear, data: dict) -> MsaAdjustment:
    if fy.status == "closed":
        raise MsaError("Exercice clôturé : assiette figée.", status=409)
    person = _person(data.get("person_id"))
    kind = data.get("kind")
    if kind not in MSA_ADJUSTMENT_KINDS:
        raise MsaError("Type de ligne inconnu.", "kind")
    amount = data.get("amount_cents")
    if isinstance(amount, bool) or not isinstance(amount, int) or not 0 < amount <= 10 ** 11:
        raise MsaError("Montant positif en centimes attendu.", "amount_cents")
    reason = str(data.get("reason") or "").strip()[:300] or None
    if kind != "avaloir" and (reason is None or len(reason) < 5):
        raise MsaError("Motif obligatoire.", "reason")
    row = MsaAdjustment(fiscal_year_id=fy.id, person_id=person.id, kind=kind, amount_cents=amount, reason=reason)
    db.session.add(row)
    return row


def delete_adjustment(fy: FiscalYear, adj_id: int) -> None:
    if fy.status == "closed":
        raise MsaError("Exercice clôturé : assiette figée.", status=409)
    row = MsaAdjustment.query.filter_by(id=adj_id, fiscal_year_id=fy.id).first()
    if row is None:
        raise MsaError("Ligne introuvable.", status=404)
    db.session.delete(row)


def update_person(person_id: int, data: dict) -> MsaPerson:
    person = _person(person_id)
    if "status" in data:
        if data["status"] not in MSA_STATUSES:
            raise MsaError("Statut inconnu.", "status")
        person.status = data["status"]
    if "base_option" in data:
        if data["base_option"] not in MSA_BASE_OPTIONS:
            raise MsaError("Option d'assiette inconnue.", "base_option")
        person.base_option = data["base_option"]
    if "option_since" in data:
        raw = data["option_since"]
        try:
            person.option_since = date.fromisoformat(raw) if raw else None
        except (TypeError, ValueError):
            raise MsaError("Date attendue (AAAA-MM-JJ).", "option_since") from None
    if "atexa_category" in data:
        if data["atexa_category"] not in (None, "", "A", "B", "C", "D", "E"):
            raise MsaError("Catégorie de risques A à E attendue.", "atexa_category")
        person.atexa_category = data["atexa_category"] or None
    if "note" in data:
        person.note = str(data["note"] or "").strip()[:300] or None
    return person

