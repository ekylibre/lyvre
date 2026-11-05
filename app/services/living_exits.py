"""Sorties de biens vivants, réinvestissement après abattage sanitaire, dépréciations (lot AG5.c,
claudedocs/design_biens_vivants.md § 2 et § 4, AGD22).

- **Sorties typées** : cession, mort, sinistre, abattage sanitaire, mise au rebut ; totales ou partielles (coût moyen,
  AG5.a). Valeur nette en **6571** ; prix de cession ou indemnité (assurance, État) en **7571** (Q-B4), créance en 462.
- **Abattage sanitaire** : registre de réinvestissement (indemnité, valeur nette, reconstitution du cheptel dans les
  2 ans), lu par AG6 pour l'exonération et la réintégration de la part non réinvestie (art. 75-0 D, à vérifier) ;
  rappel dans l'échéancier.
- **Dépréciation** (294) : montant cumulé voulu à la clôture, par fiche, avec motif ; l'écriture gérée
  `LIVING_IMPAIRMENT` passe la différence avec la clôture précédente (D 68164 / C 294, ou D 294 / C 78164) ; un bien
  sorti voit sa dépréciation reprise.
"""
from __future__ import annotations

from datetime import date

from app.extensions import db
from app.models import Account, Asset, AssetImpairment, AssetLivingExit, FiscalYear, JournalEntry, LivingReinvestment
from app.models.asset import LIVING_EXIT_KINDS
from app.models.journal_entry import SOURCE_LIVING_IMPAIRMENT
from app.services import assets
from app.services.assets import AssetError

INDEMNITY_KINDS = ("death", "casualty", "sanitary_slaughter")


def _account(code: str, label: str | None = None, kind: str = "REVENUE", parent_code: str | None = None) -> Account:
    account = Account.query.filter_by(code=code, is_header=False).first()
    if account is None:
        if label is None:
            raise AssetError(f"Compte {code} absent du plan : créez-le d'abord.", status=409)
        parent = Account.query.filter_by(code=parent_code).first() if parent_code else None
        account = Account(code=code, label=label, account_type=kind, parent_id=parent.id if parent else None)
        db.session.add(account)
        db.session.flush()
    return account


def _plus_two_years(day: date) -> date:
    try:
        return day.replace(year=day.year + 2)
    except ValueError:                                    # 29 février
        return day.replace(year=day.year + 2, day=28)


# ------------------------------------------------------------------ sorties

def exit_living(asset: Asset, data: dict, user_id=None) -> AssetLivingExit:
    from app.services.ledger import post_entry

    unknown = set(data) - {"date", "kind", "units", "price_cents", "indemnity_cents", "sale_id", "note"}
    if unknown:
        raise AssetError(f"Champ inconnu : {sorted(unknown)[0]}.", sorted(unknown)[0], 422)
    if not assets.is_living(asset.account):
        raise AssetError("Sortie réservée aux biens vivants (24x).", "kind", 422)
    kind = data.get("kind")
    if kind not in LIVING_EXIT_KINDS:
        raise AssetError("Type de sortie inconnu.", "kind", 422)
    try:
        on = date.fromisoformat(str(data.get("date") or "")[:10])
    except ValueError:
        raise AssetError("Date de sortie : AAAA-MM-JJ.", "date", 422) from None

    def cents(key):
        value = data.get(key) or 0
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AssetError("Montant positif en centimes attendu.", key, 422)
        return value

    price, indemnity = cents("price_cents"), cents("indemnity_cents")
    if kind != "sale" and price:
        raise AssetError("Un prix ne s'indique que pour une cession (indemnité pour une mort, un sinistre, un abattage).",
                         "price_cents", 422)
    if indemnity and kind not in INDEMNITY_KINDS:
        raise AssetError("Indemnité réservée à la mort, au sinistre et à l'abattage sanitaire.", "indemnity_cents", 422)
    units = data.get("units")
    target, entry = assets.living_exit(asset, on, units, "sold" if kind == "sale" else "scrapped", price,
                                       data.get("sale_id") if isinstance(data.get("sale_id"), int) else None, user_id)
    book_value_id = (assets._living_account("6571") or assets._role("disposal_book_value")).id  # noqa: SLF001
    book_value = sum(l.debit_cents for l in entry.lines if l.account_id == book_value_id)
    row = AssetLivingExit(asset_id=target.id, on=on, kind=kind, units=assets.units_of(target), price_cents=price or None,
                          indemnity_cents=indemnity or None, book_value_cents=book_value, entry_id=entry.id,
                          note=(str(data.get("note") or "").strip()[:300]) or None)
    db.session.add(row)
    if indemnity:
        label = f"Indemnité — {LIVING_EXIT_KINDS[kind].lower()} — {target.label}"[:300]
        fy = assets._fy_for(on)  # noqa: SLF001
        row.indemnity_entry_id = post_entry(fy.id, assets._journal().id, on, label, [  # noqa: SLF001
            {"account_id": _account("462").id, "label": label, "debit_cents": indemnity, "credit_cents": 0},
            {"account_id": _account("7571").id, "label": label, "debit_cents": 0, "credit_cents": indemnity}],
            source="ASSET", commit=False).id
    db.session.flush()
    if kind == "sanitary_slaughter":
        db.session.add(LivingReinvestment(exit_id=row.id, indemnity_cents=indemnity, book_value_cents=book_value,
                                          deadline=_plus_two_years(on)))
        db.session.flush()
    return row


def exit_payload(row: AssetLivingExit) -> dict:
    r = row.reinvestment
    return {"id": row.id, "asset_id": row.asset_id, "label": row.asset.label, "on": row.on.isoformat(), "kind": row.kind,
            "kind_label": LIVING_EXIT_KINDS[row.kind], "units": row.units, "price_cents": row.price_cents,
            "indemnity_cents": row.indemnity_cents, "book_value_cents": row.book_value_cents, "note": row.note,
            "reinvestment": reinvestment_payload(r) if r is not None else None}


def reinvestment_payload(r: LivingReinvestment) -> dict:
    return {"id": r.id, "exit_id": r.exit_id, "indemnity_cents": r.indemnity_cents, "book_value_cents": r.book_value_cents,
            "gain_cents": r.indemnity_cents - r.book_value_cents, "deadline": r.deadline.isoformat(),
            "reinvested_cents": r.reinvested_cents, "reinvested_on": r.reinvested_on.isoformat() if r.reinvested_on else None,
            "remaining_cents": max(r.indemnity_cents - r.reinvested_cents, 0), "note": r.note,
            "label": r.exit.asset.label, "on": r.exit.on.isoformat()}


def update_reinvestment(r: LivingReinvestment, data: dict) -> LivingReinvestment:
    unknown = set(data) - {"reinvested_cents", "reinvested_on", "note"}
    if unknown:
        raise AssetError(f"Champ inconnu : {sorted(unknown)[0]}.", sorted(unknown)[0], 422)
    if "reinvested_cents" in data:
        value = data["reinvested_cents"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise AssetError("Montant réinvesti positif attendu.", "reinvested_cents", 422)
        r.reinvested_cents = value
    if "reinvested_on" in data:
        try:
            r.reinvested_on = date.fromisoformat(str(data["reinvested_on"])[:10]) if data["reinvested_on"] else None
        except ValueError:
            raise AssetError("Date : AAAA-MM-JJ.", "reinvested_on", 422) from None
    if "note" in data:
        r.note = (str(data["note"] or "").strip()[:300]) or None
    db.session.flush()
    return r


# ------------------------------------------------------------------ dépréciations

def impairment_entry(fy: FiscalYear) -> JournalEntry | None:
    return JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_LIVING_IMPAIRMENT).first()


def _previous(asset_id: int, fy: FiscalYear) -> int:
    row = (AssetImpairment.query.join(FiscalYear, FiscalYear.id == AssetImpairment.fiscal_year_id)
           .filter(AssetImpairment.asset_id == asset_id, AssetImpairment.entry_id.isnot(None),
                   FiscalYear.end_date < fy.start_date).order_by(FiscalYear.end_date.desc()).first())
    return row.amount_cents if row is not None else 0


def _living_assets(fy: FiscalYear) -> list[Asset]:
    out = []
    for asset in Asset.query.filter(Asset.parent_id.is_(None)).order_by(Asset.id):
        if not assets.is_living(asset.account) or asset.account.code.startswith("234"):
            continue
        gone = asset.status in ("sold", "scrapped") and asset.disposal_date and asset.disposal_date < fy.start_date
        if not gone and asset.acquired_on <= fy.end_date:
            out.append(asset)
    return out


def impairment_rows(fy: FiscalYear) -> list[dict]:
    stored = {r.asset_id: r for r in AssetImpairment.query.filter_by(fiscal_year_id=fy.id)}
    out = []
    for asset in _living_assets(fy):
        previous = _previous(asset.id, fy)
        row = stored.get(asset.id)
        exited = asset.status in ("sold", "scrapped")
        if row is None and not previous and exited:
            continue
        wanted = 0 if exited else (row.amount_cents if row is not None else previous)
        out.append({"asset_id": asset.id, "label": asset.label, "account_code": asset.account.code,
                    "net_cents": assets.payload(asset)["net_cents"], "previous_cents": previous, "amount_cents": wanted,
                    "delta_cents": wanted - previous, "reason": row.reason if row is not None else None,
                    "exited": exited, "saved": row is not None, "posted": bool(row and row.entry_id)})
    return out


def set_impairment(fy: FiscalYear, asset_id, amount, reason) -> AssetImpairment:
    if fy.status != "open":
        raise AssetError("Exercice clôturé : dépréciations figées.", status=409)
    if impairment_entry(fy) is not None:
        raise AssetError("Écriture des dépréciations passée : annulez-la avant de modifier.", status=409)
    asset = db.session.get(Asset, asset_id) if isinstance(asset_id, int) and not isinstance(asset_id, bool) else None
    if asset is None or asset not in _living_assets(fy) or asset.status in ("sold", "scrapped"):
        raise AssetError("Bien vivant en service introuvable.", "asset_id", 404)
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise AssetError("Dépréciation cumulée positive (ou nulle) attendue.", "amount_cents", 422)
    if amount > assets.payload(asset)["net_cents"]:
        raise AssetError("La dépréciation dépasse la valeur nette du bien.", "amount_cents", 422)
    text = (str(reason or "").strip()[:300]) or None
    if amount != _previous(asset.id, fy) and (text is None or len(text) < 5):
        raise AssetError("Motif obligatoire (5 caractères au moins) : état sanitaire, valeur de marché, sinistre…", "reason", 422)
    row = AssetImpairment.query.filter_by(asset_id=asset.id, fiscal_year_id=fy.id).first()
    if row is None:
        row = AssetImpairment(asset_id=asset.id, fiscal_year_id=fy.id, amount_cents=amount)
        db.session.add(row)
    row.amount_cents, row.reason = amount, text
    db.session.flush()
    return row


def cancel_impairments(fy: FiscalYear) -> None:
    from app.services.ledger import delete_entries

    entry = impairment_entry(fy)
    if entry is None:
        return
    if fy.status != "open":
        raise AssetError("Exercice clôturé : dépréciations figées.", status=409)
    if entry.is_validated:
        raise AssetError("Écriture des dépréciations validée : annulez d'abord son lot de validation.", status=409)
    for row in AssetImpairment.query.filter_by(fiscal_year_id=fy.id, entry_id=entry.id):
        row.entry_id = None
    db.session.flush()
    (outcome,) = delete_entries([entry.id], allow_managed=True)
    if outcome["status"] != "ok":
        raise AssetError(outcome.get("message") or "Suppression impossible.", status=409)


def post_impairments(fy: FiscalYear) -> JournalEntry | None:
    """Passe (ou repasse) les dépréciations de l'exercice : différences avec la clôture précédente (sans commit)."""
    from app.services.ledger import post_entry

    if not assets.enabled():
        raise AssetError("Écritures réservées aux exploitations au réel (partie double).", status=409)
    if fy.status != "open":
        raise AssetError("Exercice clôturé : rouvrez-le pour passer les dépréciations.", status=409)
    cancel_impairments(fy)
    rows = impairment_rows(fy)
    lines, keep = [], []
    impairment = _account("294")
    for r in rows:
        stored = AssetImpairment.query.filter_by(asset_id=r["asset_id"], fiscal_year_id=fy.id).first()
        if stored is None and (r["delta_cents"] or r["exited"]):
            stored = AssetImpairment(asset_id=r["asset_id"], fiscal_year_id=fy.id, amount_cents=r["amount_cents"],
                                     reason="Sortie du bien : reprise" if r["exited"] else None)
            db.session.add(stored)
        if stored is None:
            continue
        stored.amount_cents = r["amount_cents"]
        keep.append(stored)
        delta, text = r["delta_cents"], f"Dépréciation — {r['label']}"[:300]
        if delta > 0:
            lines += [{"account_id": _account("68164").id, "label": text, "debit_cents": delta, "credit_cents": 0},
                      {"account_id": impairment.id, "label": text, "debit_cents": 0, "credit_cents": delta}]
        elif delta < 0:
            reversal = _account("78164", "Biens vivants immobilisés", "REVENUE", "7816")
            lines += [{"account_id": impairment.id, "label": text, "debit_cents": -delta, "credit_cents": 0},
                      {"account_id": reversal.id, "label": text, "debit_cents": 0, "credit_cents": -delta}]
    db.session.flush()
    if not lines:
        for stored in keep:
            stored.entry_id = None
        return None
    entry = post_entry(fy.id, assets._journal().id, fy.end_date, f"Dépréciations des biens vivants {fy.label}", lines,  # noqa: SLF001
                       source=SOURCE_LIVING_IMPAIRMENT, commit=False)
    for stored in keep:
        stored.entry_id = entry.id
    db.session.flush()
    return entry


# ------------------------------------------------------------------ contrôles et échéancier

def checks(fy: FiscalYear) -> list[tuple[str, str, int, str]]:
    if not assets.enabled():
        return []
    out = []
    rows = impairment_rows(fy)
    if impairment_entry(fy) is None and any(r["delta_cents"] for r in rows):
        out.append(("living_impairment", "Dépréciations de biens vivants à passer (nouvelles, modifiées ou à reprendre)",
                    sum(1 for r in rows if r["delta_cents"]), "anomaly"))
    from datetime import timedelta
    horizon = fy.end_date + timedelta(days=183)
    soon = [r for r in LivingReinvestment.query.all()
            if r.reinvested_on is None and r.deadline <= horizon and r.reinvested_cents < r.indemnity_cents]
    if soon:
        out.append(("living_reinvestment", "Abattage sanitaire : cheptel à reconstituer dans le délai de 2 ans (exonération, "
                    "AG6)", len(soon), "info"))
    return out


def agenda_occurrences(start: date, end: date) -> list[dict]:
    """Règle `lyvre` de source `living_reinvestments` : date limite de reconstitution du cheptel."""
    out = []
    for r in LivingReinvestment.query.filter(LivingReinvestment.deadline.between(start, end)):
        out.append({"date": r.deadline, "period": f"{r.exit.asset.label} (abattage du {r.exit.on:%d/%m/%Y})",
                    "lyvre_status": "declared" if r.reinvested_on else None, "amount_cents": r.indemnity_cents,
                    "link": "/assets/?living=1"})
    return out
