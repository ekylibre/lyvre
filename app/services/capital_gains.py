"""Plus-values professionnelles et crédits d'impôt BA (lot AG6.g, claudedocs/design_fiscalite_ba.md § 9, AGD23 Q-F7 ;
audit § 3.6 et § 3.8). Seuils et montants en paramètres datés `ba.pv.*` et `ba.credit.*`, **à valider**.

- **Plus-values** de l'exercice, par immobilisation cédée ou mise au rebut : prix − valeur nette (coût − amortissements).
  Court terme / long terme (art. 39 duodecies) : bien détenu moins de 2 ans, tout à court terme ; au-delà, la
  plus-value est à court terme à hauteur des amortissements et à long terme au-delà, la moins-value à court terme
  pour un bien amortissable et à long terme sinon. Les sorties d'abattage sanitaire (registre 75-0 D) sont écartées.
- **Lignes de passage** : plus-value nette à long terme retirée du bénéfice (imposée à part ou exonérée), moins-value
  nette à long terme réintégrée (reportable 10 ans) ; sur option, exonération 151 septies de la plus-value nette à court
  terme, au taux du contribuable.
- **151 septies** : activité depuis 5 ans au moins ; moyenne des recettes HT (façon × 3) des 2 années civiles qui
  précèdent la clôture ; exonération totale jusqu'au premier seuil, dégressive jusqu'au second (seuils relevés pour une
  cession à un jeune agriculteur) ; en société civile non IS, taux par associé sur sa quote-part de recettes (art. 70).
- **Crédits d'impôt** : bio (recettes AB ≥ 40 %, montant forfaitaire, × associés en GAEC), HVE (2 500 € une fois, certification valide
  à la clôture, exercices clos jusqu'au 31/12/2026), remplacement pour congés (taux × dépenses, dans la limite de jours) ; répartition par associé.
"""
from __future__ import annotations

import json
from datetime import date

from app.extensions import db
from app.models import Asset, AssetLivingExit, CapitalGainChoice, FiscalYear, LivingReinvestment, TaxCredit
from app.models.tax_result import TAX_CREDIT_KINDS
from app.services import reg_params
from app.services.tax_result import TaxResultError


def _p(key: str, fy: FiscalYear, default=None):
    return reg_params.value(key, fy.end_date, default=default)


def _years_after(start: date, years: int) -> date:
    try:
        return start.replace(year=start.year + years)
    except ValueError:                                     # 29 février
        return start.replace(year=start.year + years, day=28)


# ------------------------------------------------------------------ plus-values par bien

def _slaughtered(asset_ids: set[int]) -> set[int]:
    if not asset_ids:
        return set()
    rows = (db.session.query(AssetLivingExit.asset_id).join(LivingReinvestment, LivingReinvestment.exit_id == AssetLivingExit.id)
            .filter(AssetLivingExit.asset_id.in_(asset_ids)).all())
    return {r[0] for r in rows}


def disposals(fy: FiscalYear) -> list[dict]:
    from app.services import assets
    roots = (Asset.query.filter(Asset.parent_id.is_(None), Asset.status.in_(("sold", "scrapped")),
                                Asset.disposal_date.between(fy.start_date, fy.end_date)).order_by(Asset.disposal_date, Asset.id).all())
    excluded = _slaughtered({a.id for a in roots})
    out = []
    for asset in roots:
        parts = assets.leaves(asset)
        cost = sum(p.acquisition_cents for p in parts)
        depreciation = sum(assets.accumulated(p) for p in parts) if assets.enabled() else 0
        net = cost - depreciation
        price = asset.disposal_price_cents or 0
        gain = price - net
        long_held = asset.disposal_date >= _years_after(asset.acquired_on, 2)
        depreciable = any(p.method != "none" for p in parts)
        if not long_held:
            short, long_ = gain, 0
        elif gain >= 0:
            short = min(gain, depreciation)
            long_ = gain - short
        else:
            short, long_ = (gain, 0) if depreciable else (0, gain)
        out.append({"asset_id": asset.id, "label": asset.label, "account": asset.account.code, "acquired_on": asset.acquired_on.isoformat(),
                    "disposed_on": asset.disposal_date.isoformat(), "kind": asset.status, "cost_cents": cost,
                    "depreciation_cents": depreciation, "net_cents": net, "price_cents": price, "gain_cents": gain,
                    "long_held": long_held, "depreciable": depreciable, "short_cents": short, "long_cents": long_,
                    "excluded": asset.id in excluded,
                    "excluded_reason": "abattage sanitaire (registre 75-0 D)" if asset.id in excluded else None})
    return out


# ------------------------------------------------------------------ 151 septies

def choice(fy: FiscalYear) -> CapitalGainChoice | None:
    return CapitalGainChoice.query.filter_by(fiscal_year_id=fy.id).first()


def exemption_rate(receipts: int | None, fy: FiscalYear, young_buyer: bool) -> tuple[int | None, str]:
    """Taux d'exonération en points de base pour une moyenne de recettes, avec le détail."""
    prefix = "ba.pv.ja_" if young_buyer else "ba.pv."
    full, partial = _p(f"{prefix}full_cents", fy), _p(f"{prefix}partial_cents", fy)
    if full is None or partial is None:
        return None, "Seuils de l'art. 151 septies introuvables pour la date de clôture."
    if receipts is None:
        return None, "Recettes inconnues : saisissez les années manquantes (Structure › Fiscalité)."
    if receipts <= full:
        return 10000, "exonération totale"
    if receipts >= partial:
        return 0, "recettes au-delà du seuil : pas d'exonération"
    rate = round((partial - receipts) * 10000 / (partial - full))
    return rate, f"exonération partielle : (seuil haut − recettes) ÷ {round((partial - full) / 100):,} €".replace(",", " ")


def septies(fy: FiscalYear) -> dict:
    from app.services import ba_regimes, organization, tax_result
    row = choice(fy)
    since = (row.activity_since if row and row.activity_since else organization.get().created_on)
    years = _p("ba.pv.activity_years", fy, 5) or 5
    young = bool(row and row.young_farmer_buyer)
    reason = None
    if since is None:
        reason = "Date de début d'activité inconnue (condition des 5 ans)."
    elif _years_after(since, years) > fy.end_date:
        reason = f"Activité exercée depuis moins de {years} ans à la clôture."
    year = fy.end_date.year
    receipts = [ba_regimes.year_receipts(y) for y in (year - 2, year - 1)]
    known = [r["threshold_cents"] for r in receipts if r["threshold_cents"] is not None]
    missing = [r["year"] for r in receipts if r["threshold_cents"] is None]
    # Moyenne des 2 années civiles ; une année inconnue compte pour 0 : la moyenne n'est alors qu'un minimum, qui ne
    # conclut que s'il dépasse déjà le seuil haut (pas d'exonération, quelle que soit l'année manquante).
    average = round(sum(known) / 2) if known and not missing else None
    floor = round(sum(known) / 2) if known and missing else None

    def rate_for(part_avg, part_floor):
        if part_avg is not None:
            return exemption_rate(part_avg, fy, young)
        if part_floor is not None:
            rate, detail = exemption_rate(part_floor, fy, young)
            if rate is None:                                         # barème absent pour la date de clôture
                return None, detail
            if rate == 0:
                return 0, f"recettes au-delà du seuil même en comptant {', '.join(map(str, missing))} pour 0 : pas d'exonération"
        return None, f"recettes {', '.join(map(str, missing))} inconnues : saisissez-les (Structure › Fiscalité)"

    associates = []
    company_is = tax_result._is_company_is(fy)  # noqa: SLF001
    rows, _ = ([], []) if company_is else tax_result.shares(fy)
    if rows:                                                         # art. 70 : quote-part de recettes par associé
        for r in rows:
            share = lambda v: round(v * r["share_bp"] / 10000) if v is not None else None  # noqa: E731
            part = share(average)
            rate, detail = rate_for(part, share(floor))
            associates.append({"associate_id": r["associate_id"], "name": r["name"], "share_bp": r["share_bp"],
                               "receipts_cents": part, "rate_bp": None if reason and rate != 0 else rate, "detail": detail})
        rated = [a for a in associates if a["rate_bp"] is not None]
        rate = round(sum(a["rate_bp"] * a["share_bp"] for a in rated) / 10000) if rated and len(rated) == len(associates) else None
        detail = (associates[0]["detail"] if len(associates) == 1
                  else "taux moyen pondéré des associés (recettes au prorata des droits)")
    else:
        rate, detail = rate_for(average, floor)
    if reason and rate != 0:                                         # 0 % : acquis quelle que soit l'ancienneté
        rate = None
    return {"activity_since": since.isoformat() if since else None, "young_farmer_buyer": young, "receipts": receipts,
            "average_cents": average, "missing_years": missing, "rate_bp": rate, "detail": detail, "reason": reason, "associates": associates,
            "applied": bool(row and row.apply_151_septies)}


def totals(fy: FiscalYear) -> dict:
    items = [d for d in disposals(fy) if not d["excluded"]]
    return {"short_cents": sum(d["short_cents"] for d in items), "long_cents": sum(d["long_cents"] for d in items)}


def tax_lines(fy: FiscalYear) -> list[dict]:
    t = totals(fy)
    lines = []
    if t["long_cents"] > 0:
        lines.append({"key": "pv_long_term", "source": "capital_gains", "amount_cents": -t["long_cents"], "to_validate": True,
                      "label": "Plus-value nette à long terme retirée du bénéfice (imposée à part ou exonérée)"})
    elif t["long_cents"] < 0:
        lines.append({"key": "mv_long_term", "source": "capital_gains", "amount_cents": -t["long_cents"], "to_validate": True,
                      "label": "Moins-value nette à long terme réintégrée (imputable sur les plus-values à long terme des 10 exercices suivants)"})
    row = choice(fy)
    if row and row.apply_151_septies and t["short_cents"] > 0:
        rate = septies(fy)["rate_bp"]
        if rate:
            lines.append({"key": "pv_151_septies", "source": "capital_gains", "amount_cents": -round(t["short_cents"] * rate / 10000),
                          "to_validate": True,
                          "label": f"Plus-value nette à court terme exonérée (art. 151 septies, {rate / 100:.2f} %)".replace(".", ",")})
    return lines


def view(fy: FiscalYear) -> dict:
    t = totals(fy)
    info = septies(fy)
    rate = info["rate_bp"] or 0
    long_ = max(t["long_cents"], 0)
    return {"disposals": disposals(fy), "short_cents": t["short_cents"], "long_cents": t["long_cents"], "septies": info,
            "long_exempt_cents": round(long_ * rate / 10000) if info["applied"] else 0,
            "long_taxable_cents": long_ - (round(long_ * rate / 10000) if info["applied"] else 0),
            "short_exempt_cents": round(max(t["short_cents"], 0) * rate / 10000) if info["applied"] else 0,
            "lines": tax_lines(fy)}


def save_choice(fy: FiscalYear, data: dict) -> CapitalGainChoice:
    if fy.status == "closed":
        raise TaxResultError("Exercice clôturé : le résultat fiscal est figé.", status=409)
    row = choice(fy) or CapitalGainChoice(fiscal_year_id=fy.id)
    for field in ("apply_151_septies", "young_farmer_buyer"):
        if field in data:
            if not isinstance(data[field], bool):
                raise TaxResultError("Vrai ou faux attendu.", field)
            setattr(row, field, data[field])
    if "activity_since" in data:
        raw = data["activity_since"]
        try:
            row.activity_since = date.fromisoformat(raw) if raw else None
        except (TypeError, ValueError):
            raise TaxResultError("Date au format AAAA-MM-JJ attendue.", "activity_since") from None
    db.session.add(row)
    db.session.flush()
    return row


# ------------------------------------------------------------------ crédits d'impôt

def _credit_amount(fy: FiscalYear, kind: str, data: dict) -> dict:
    from app.services import ba_regimes
    if kind == "organic":
        amount, ratio = _p("ba.credit.organic.amount_cents", fy), _p("ba.credit.organic.ratio_bp", fy)
        organic = data.get("organic_receipts_cents") or 0
        receipts = ba_regimes.lyvre_receipts(fy.end_date.year) or {}
        total = data.get("total_receipts_cents") or sum(receipts.get(k, 0) for k in ("agricultural_ht", "custom_work_ht", "accessory_ht"))
        share = round(organic * 10000 / total) if total else None
        eligible = amount is not None and ratio is not None and share is not None and share >= ratio
        from app.services.dep import operators
        multiplier = operators(fy) if ba_regimes._form() == "GAEC" else 1  # noqa: SLF001
        return {"amount_cents": amount * multiplier if eligible else 0, "share_bp": share, "total_receipts_cents": total,
                "detail": (f"recettes bio {share / 100:.1f} % (minimum {ratio / 100:.0f} %)".replace(".", ",") if share is not None and ratio
                           else "recettes de l'exercice inconnues") + (f", × {multiplier} associés (GAEC)" if multiplier > 1 else ""),
                "de_minimis": True}
    if kind == "hve":
        amount = _p("ba.credit.hve.amount_cents", fy)
        raw = data.get("certified_on")
        try:
            certified = date.fromisoformat(raw) if raw else None
        except ValueError:
            certified = None
        eligible = amount is not None and certified is not None and certified <= fy.end_date
        if amount is None:
            return {"amount_cents": 0, "detail": "pas de crédit HVE paramétré pour un exercice clos à cette date "
                                                 "(dispositif prévu jusqu'aux exercices clos le 31/12/2026)"}
        if certified is None:
            return {"amount_cents": 0, "detail": "date de certification à saisir"}
        if not eligible:
            return {"amount_cents": 0, "detail": f"certification du {certified:%d/%m/%Y} postérieure à la clôture"}
        return {"amount_cents": amount, "de_minimis": True,
                "detail": f"certification du {certified:%d/%m/%Y} valide à la clôture ; crédit accordé une seule fois "
                          "(vérifier qu'il n'a pas déjà été obtenu), réparti entre associés"}
    rate, limit = _p("ba.credit.replacement.rate_bp", fy), _p("ba.credit.replacement.days", fy)
    expense, days = data.get("expense_cents") or 0, data.get("days") or 0
    if rate is None or limit is None or not days:
        return {"amount_cents": 0, "detail": "dépenses et nombre de jours à saisir"}
    amount = round(expense * rate / 10000 * min(days, limit) / days)
    return {"amount_cents": amount, "detail": f"{rate / 100:.0f} % des dépenses, {min(days, limit)} jour(s) retenu(s) sur {days}"}


def credits(fy: FiscalYear) -> dict:
    from app.services import tax_result
    company_is = tax_result._is_company_is(fy)  # noqa: SLF001
    rows, _ = ([], []) if company_is else tax_result.shares(fy)
    items = []
    for credit in TaxCredit.query.filter_by(fiscal_year_id=fy.id).order_by(TaxCredit.id):
        data = json.loads(credit.data_json or "{}")
        result = _credit_amount(fy, credit.kind, data)
        split = [{"associate_id": r["associate_id"], "name": r["name"], "amount_cents": part}
                 for r, part in zip(rows, tax_result._split(result["amount_cents"], rows))]  # noqa: SLF001
        items.append({"id": credit.id, "kind": credit.kind, "label": TAX_CREDIT_KINDS[credit.kind], "data": data,
                      "note": credit.note, **result, "associates": split})
    return {"items": items, "total_cents": sum(i["amount_cents"] for i in items), "company_is": company_is,
            "kinds": [{"value": k, "label": v} for k, v in TAX_CREDIT_KINDS.items()],
            "notes": ["Montants et conditions à valider (lois de finances 2026) ; le crédit bio relève du régime de minimis.",
                      "Société à l'IS : comptabiliser la créance D 444 / C 699." if company_is else
                      "Imposition à l'IR : le crédit s'impute sur l'impôt du foyer de chaque associé, sans écriture."]}


def save_credit(fy: FiscalYear, kind: str, data: dict) -> TaxCredit:
    if fy.status == "closed":
        raise TaxResultError("Exercice clôturé.", status=409)
    if kind not in TAX_CREDIT_KINDS:
        raise TaxResultError("Crédit d'impôt inconnu.", "kind")
    clean = {}
    for field in ("organic_receipts_cents", "total_receipts_cents", "expense_cents", "days"):
        value = data.get(field)
        if value in (None, ""):
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise TaxResultError("Nombre positif attendu.", field)
        clean[field] = value
    if data.get("certified_on"):
        try:
            clean["certified_on"] = date.fromisoformat(data["certified_on"]).isoformat()
        except (TypeError, ValueError):
            raise TaxResultError("Date au format AAAA-MM-JJ attendue.", "certified_on") from None
    row = TaxCredit.query.filter_by(fiscal_year_id=fy.id, kind=kind).first() or TaxCredit(fiscal_year_id=fy.id, kind=kind)
    row.data_json = json.dumps(clean)
    row.note = (str(data.get("note") or "").strip()[:300]) or None
    db.session.add(row)
    db.session.flush()
    return row


def delete_credit(fy: FiscalYear, kind: str) -> None:
    if fy.status == "closed":
        raise TaxResultError("Exercice clôturé.", status=409)
    row = TaxCredit.query.filter_by(fiscal_year_id=fy.id, kind=kind).first()
    if row is None:
        raise TaxResultError("Crédit d'impôt introuvable.", status=404)
    db.session.delete(row)
    db.session.flush()
