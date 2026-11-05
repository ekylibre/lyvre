"""Biens vivants en cours et entrées en immobilisation (lot AG5.b, claudedocs/design_biens_vivants.md § 2 et § 4, AGD22).

- **En-cours (234x)** : à la clôture, les coûts de croissance de l'exercice d'un bien vivant encore en cours (saisis,
  avec leur base : coût réel, barème) passent en D 234x / C **7222** (production immobilisée, biens vivants), écriture
  gérée `LIVING_WIP` au dernier jour, non extournée. La valeur d'origine de la fiche en cours augmente d'autant : la
  mise en service (existante) virera le cumul en 24x.
- **Mise en service** : compte définitif proposé selon l'en-cours (2341 → 241, 2343 → 243, 2346 → 246, 2347 → 247).
- **Animal du stock devenu reproducteur** (mouvement « sortie vers les immobilisations » d'un lot d'AG4.b) : fiche
  immobilisée en service à la date, à sa valeur (stock ou coût de production), D 24x / C **724** ; nouvelle fiche ou
  composant d'un lot existant. Supprimer le mouvement annule la fiche et son écriture tant qu'elles ne sont pas figées.
"""
from __future__ import annotations

from datetime import date

from app.extensions import db
from app.models import Account, Asset, FiscalYear, JournalEntry, LivingWipCost, StockLot, StockLotMovement
from app.models.journal_entry import SOURCE_LIVING_WIP
from app.services import assets
from app.services.assets import AssetError

IN_SERVICE_ACCOUNTS = {"2341": "241", "2343": "243", "2346": "246", "2347": "247"}


def _account(code: str) -> Account:
    account = Account.query.filter_by(code=code, is_header=False).first()
    if account is None:
        raise AssetError(f"Compte {code} absent du plan : créez-le d'abord.", status=409)
    return account


def in_service_account(asset: Asset) -> Account | None:
    """Compte définitif proposé à la mise en service d'un bien vivant en cours."""
    code = next((target for prefix, target in IN_SERVICE_ACCOUNTS.items() if asset.account.code.startswith(prefix)), None)
    return Account.query.filter_by(code=code, is_header=False).first() if code else None


# ------------------------------------------------------------------ en-cours (234x)

def wip_assets(fy: FiscalYear) -> list[Asset]:
    """Biens vivants en cours à la clôture (fiches en attente sur 234x)."""
    return [a for a in Asset.query.filter(Asset.status == "waiting").order_by(Asset.id)
            if a.account.code.startswith("234") and a.acquired_on <= fy.end_date]


def wip_entry(fy: FiscalYear) -> JournalEntry | None:
    return JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_LIVING_WIP).first()


def wip_rows(fy: FiscalYear) -> list[dict]:
    costs = {c.asset_id: c for c in LivingWipCost.query.filter_by(fiscal_year_id=fy.id)}
    ids = {a.id for a in wip_assets(fy)} | set(costs)
    out = []
    for asset_id in sorted(ids):
        asset = db.session.get(Asset, asset_id)
        cost = costs.get(asset_id)
        out.append({"asset_id": asset.id, "label": asset.label, "account_code": asset.account.code,
                    "status": asset.status, "acquisition_cents": asset.acquisition_cents,
                    "units": asset.units, "species": asset.species,
                    "amount_cents": cost.amount_cents if cost else None, "basis": cost.basis if cost else None,
                    "posted": bool(cost and cost.entry_id)})
    return out


def _require_open(fy: FiscalYear) -> None:
    if fy.status != "open":
        raise AssetError("Exercice clôturé : les en-cours sont figés.", status=409)


def set_wip_cost(fy: FiscalYear, asset_id, amount, basis=None) -> LivingWipCost | None:
    _require_open(fy)
    if wip_entry(fy) is not None:
        raise AssetError("Écriture des en-cours passée : annulez-la avant de modifier les coûts.", status=409)
    asset = db.session.get(Asset, asset_id) if isinstance(asset_id, int) and not isinstance(asset_id, bool) else None
    if asset is None or asset not in wip_assets(fy):
        raise AssetError("Bien vivant en cours (234x, en attente) introuvable.", "asset_id", 404)
    row = LivingWipCost.query.filter_by(asset_id=asset.id, fiscal_year_id=fy.id).first()
    if amount in (None, 0):
        if row is not None:
            db.session.delete(row)
            db.session.flush()
        return None
    if isinstance(amount, bool) or not isinstance(amount, int) or not 0 < amount <= 10 ** 11:
        raise AssetError("Coût de croissance positif en centimes attendu.", "amount_cents", 422)
    if row is None:
        row = LivingWipCost(asset_id=asset.id, fiscal_year_id=fy.id, amount_cents=amount)
        db.session.add(row)
    row.amount_cents = amount
    row.basis = (str(basis or "").strip()[:300]) or None
    db.session.flush()
    return row


def cancel_wip(fy: FiscalYear) -> None:
    from app.services.ledger import delete_entries

    entry = wip_entry(fy)
    if entry is None:
        return
    _require_open(fy)
    if entry.is_validated:
        raise AssetError("Écriture des en-cours validée : annulez d'abord son lot de validation.", status=409)
    rows = LivingWipCost.query.filter_by(fiscal_year_id=fy.id, entry_id=entry.id).all()
    if any(r.asset.status != "waiting" for r in rows):
        raise AssetError("Un bien vivant de cette écriture est déjà mis en service : l'écriture ne s'annule plus.", status=409)
    for row in rows:
        row.asset.acquisition_cents -= row.amount_cents
        row.entry_id = None
    db.session.flush()
    (outcome,) = delete_entries([entry.id], allow_managed=True)
    if outcome["status"] != "ok":
        raise AssetError(outcome.get("message") or "Suppression impossible.", status=409)


def post_wip(fy: FiscalYear) -> JournalEntry | None:
    """Passe (ou repasse) l'écriture des en-cours de l'exercice : D 234x / C 7222 au dernier jour (sans commit)."""
    from app.services.ledger import post_entry

    if not assets.enabled():
        raise AssetError("Écritures réservées aux exploitations au réel (partie double).", status=409)
    _require_open(fy)
    cancel_wip(fy)
    rows = [r for r in LivingWipCost.query.filter_by(fiscal_year_id=fy.id) if r.asset.status == "waiting"]
    if not rows:
        return None
    production = _account("7222")
    lines = []
    for row in rows:
        text = f"En-cours — {row.asset.label}"[:300]
        lines += [{"account_id": row.asset.account_id, "label": text, "debit_cents": row.amount_cents, "credit_cents": 0},
                  {"account_id": production.id, "label": text, "debit_cents": 0, "credit_cents": row.amount_cents}]
    from app.services.assets import _journal
    entry = post_entry(fy.id, _journal().id, fy.end_date, f"Biens vivants en cours {fy.label}", lines,
                       source=SOURCE_LIVING_WIP, commit=False)
    for row in rows:
        row.entry_id = entry.id
        row.asset.acquisition_cents += row.amount_cents
    db.session.flush()
    return entry


def checks(fy: FiscalYear) -> list[tuple[str, str, int, str]]:
    if not assets.enabled():
        return []
    out = []
    rows = wip_rows(fy)
    missing = [r for r in rows if r["status"] == "waiting" and r["amount_cents"] is None]
    if missing:
        out.append(("living_wip_missing", "Biens vivants en cours (234x) sans coût de croissance de l'exercice",
                    len(missing), "info"))
    if any(r["amount_cents"] and not r["posted"] for r in rows):
        out.append(("living_wip_entry", "Coûts de croissance des biens vivants en cours saisis, écriture non passée",
                    1, "anomaly"))
    return out


# ------------------------------------------------------------------ animal du stock devenu reproducteur

def from_stock(lot: StockLot, data: dict, user_id=None) -> StockLotMovement:
    """Mouvement « sortie vers les immobilisations » + fiche immobilisée (D 24x / C 724) à la date (sans commit)."""
    from app.services import stock_lots
    from app.services.ledger import post_entry

    unknown = set(data) - {"on", "heads", "value_cents", "account_code", "parent_id", "label", "duration_months",
                           "residual_cents", "note"}
    if unknown:
        raise AssetError(f"Champ inconnu : {sorted(unknown)[0]}.", sorted(unknown)[0], 422)
    value = data.get("value_cents")
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AssetError("Valeur d'entrée (stock ou coût de production) positive attendue.", "value_cents", 422)
    parent = None
    if data.get("parent_id") is not None:
        parent = db.session.get(Asset, data["parent_id"]) if isinstance(data["parent_id"], int) else None
        if parent is None or parent.parent_id is not None or not assets.is_living(parent.account) \
                or parent.status not in ("in_use", "depreciated"):
            raise AssetError("Lot immobilisé en service introuvable.", "parent_id", 422)
    account_code = data.get("account_code") or (parent.account.code if parent else "241")
    account = _account(str(account_code))
    if not account.code.startswith("24"):
        raise AssetError("Compte de biens vivants immobilisés (24x) attendu.", "account_code", 422)
    movement = stock_lots.add_movement(lot, {"on": data.get("on"), "kind": "to_fixed_assets", "heads": data.get("heads"),
                                             "note": data.get("note")})
    duration = data.get("duration_months", parent.duration_months if parent else None)
    label = str(data.get("label") or f"{lot.label} — entrée en production").strip()[:200]
    asset = assets.save(None, {"label": label, "account_id": account.id, "acquired_on": movement.on.isoformat(),
                               "in_service_date": movement.on.isoformat(), "acquisition_cents": value,
                               "residual_cents": data.get("residual_cents") or 0,
                               "method": "linear" if duration else "none", "duration_months": duration,
                               "parent_id": parent.id if parent else None, "species": lot.species,
                               "age_class": lot.age_class, "units": movement.heads, "origin": "from_stock"})
    fy = assets._fy_for(movement.on)  # noqa: SLF001
    entry = post_entry(fy.id, assets._journal().id, movement.on, f"Entrée en production — {label}"[:500], [  # noqa: SLF001
        {"account_id": account.id, "label": label, "debit_cents": value, "credit_cents": 0},
        {"account_id": _account("724").id, "label": label, "debit_cents": 0, "credit_cents": value}],
        source="ASSET", commit=False)
    asset.in_service_entry_id = entry.id
    movement.asset_id = asset.id
    db.session.flush()
    return movement


def undo_from_stock(movement: StockLotMovement) -> None:
    """Annule la fiche créée par un mouvement « vers les immobilisations » (avant sa suppression)."""
    from app.services.ledger import delete_entries

    asset = movement.asset
    if asset is None:
        return
    if asset.depreciations or asset.status in ("sold", "scrapped"):
        raise AssetError("La fiche immobilisée a des dotations ou est sortie : le mouvement ne s'annule plus.", status=409)
    entry_id = asset.in_service_entry_id
    movement.asset_id = None
    asset.in_service_entry_id = None
    db.session.delete(asset)
    db.session.flush()
    if entry_id:
        (outcome,) = delete_entries([entry_id])
        if outcome["status"] != "ok":
            raise AssetError(outcome.get("message") or "Écriture d'entrée en production non supprimable.", status=409)
