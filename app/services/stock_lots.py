"""Lots d'animaux en stock (lot AG4.b, claudedocs/design_inventaire_agricole.md § 5.5, AGD21 Q-S8).

- Un lot réunit des animaux de même espèce, même catégorie d'âge et même destination (PCG 618-10, 3°), sur un compte
  3112 (cycle long) ou 3113 (cycle court).
- Mouvements datés en têtes : naissance, achat (ligne d'achat 60117 facultative), vente (vente facultative), mort,
  passage dans un autre lot (paire sortie / entrée), sortie vers les immobilisations (AG5).
- Effectif théorique à la clôture = ouverture + entrées − sorties de l'exercice. L'ouverture est l'effectif compté à
  la clôture précédente (ligne d'inventaire du lot) ; à défaut, un mouvement « effectif d'ouverture ».
- Aucune écriture : l'inventaire reste intermittent ; les mouvements sont un registre et un contrôle de l'effectif
  compté.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from app.extensions import db
from app.models import Account, FiscalYear, PurchaseLine, Sale, StockLine, StockLot, StockLotMovement
from app.models.stock import LOT_DESTINATIONS, LOT_IN, LOT_MOVEMENTS, LOT_OUT
from app.services.stock_inventory import StockError, classify, previous_fiscal_year

ANIMAL_CATEGORIES = ("animals_long", "animals_short")


def _fy_of(day: date) -> FiscalYear | None:
    return FiscalYear.query.filter(FiscalYear.start_date <= day, FiscalYear.end_date >= day).first()


def _open_on(day: date) -> None:
    fy = _fy_of(day)
    if fy is not None and fy.status != "open":
        raise StockError(f"Exercice {fy.label} clôturé : ses mouvements sont figés.", "on", 409)


def _text(value, limit, required=False, field=None, label=None):
    text = str(value or "").strip()[:limit]
    if required and not text:
        raise StockError(f"{label} obligatoire.", field)
    return text or None


# ------------------------------------------------------------------ lots

def _apply(lot: StockLot, data: dict, creating: bool) -> None:
    unknown = set(data) - {"label", "species", "age_class", "destination", "account_code", "average_weight_kg", "active"}
    if unknown:
        raise StockError(f"Champ inconnu : {sorted(unknown)[0]}.", sorted(unknown)[0])
    if creating or "species" in data:
        lot.species = _text(data.get("species"), 80, True, "species", "Espèce")
    if "age_class" in data:
        lot.age_class = _text(data.get("age_class"), 80)
    if creating or "label" in data:
        lot.label = _text(data.get("label"), 200) or " — ".join(x for x in (lot.species, lot.age_class) if x)
    if creating or "destination" in data:
        destination = data.get("destination") or "sale"
        if destination not in LOT_DESTINATIONS:
            raise StockError("Destination inconnue.", "destination")
        lot.destination = destination
    if creating or "account_code" in data:
        code = str(data.get("account_code") or "3113").strip()
        account = Account.query.filter_by(code=code, is_header=False).first()
        found = classify(code)
        if account is None or found is None or found[0]["key"] not in ANIMAL_CATEGORIES:
            raise StockError("Compte d'animaux en stock attendu (3112 cycle long, 3113 cycle court).", "account_code")
        if lot.id is not None and StockLine.query.filter_by(lot_id=lot.id).filter(StockLine.account_id != account.id).first():
            raise StockError("Le lot a déjà des lignes d'inventaire sur un autre compte.", "account_code", 409)
        lot.account = account
    if "average_weight_kg" in data:
        raw = data["average_weight_kg"]
        try:
            weight = None if raw in (None, "") else Decimal(str(raw).replace(",", "."))
        except InvalidOperation:
            raise StockError("Poids moyen : nombre attendu.", "average_weight_kg") from None
        if weight is not None and not Decimal(0) < weight < Decimal(100000):
            raise StockError("Poids moyen : nombre positif attendu.", "average_weight_kg")
        lot.average_weight_kg = weight
    if "active" in data:
        lot.active = bool(data["active"])


def create_lot(data: dict) -> StockLot:
    lot = StockLot()
    _apply(lot, data, creating=True)
    db.session.add(lot)
    db.session.flush()
    return lot


def update_lot(lot: StockLot, data: dict) -> StockLot:
    _apply(lot, data, creating=False)
    db.session.flush()
    return lot


def delete_lot(lot: StockLot) -> None:
    if lot.movements or StockLine.query.filter_by(lot_id=lot.id).first() is not None:
        raise StockError("Lot avec des mouvements ou des lignes d'inventaire : désactivez-le plutôt.", status=409)
    db.session.delete(lot)
    db.session.flush()


# ------------------------------------------------------------------ mouvements

def add_movement(lot: StockLot, data: dict) -> StockLotMovement:
    unknown = set(data) - {"on", "kind", "heads", "purchase_line_id", "sale_id", "counterpart_lot_id", "note"}
    if unknown:
        raise StockError(f"Champ inconnu : {sorted(unknown)[0]}.", sorted(unknown)[0])
    try:
        on = date.fromisoformat(str(data.get("on") or "")[:10])
    except ValueError:
        raise StockError("Date du mouvement : AAAA-MM-JJ.", "on") from None
    _open_on(on)
    kind = data.get("kind")
    if kind not in LOT_MOVEMENTS or kind == "transfer_in":
        raise StockError("Type de mouvement inconnu (un passage se saisit depuis le lot de départ).", "kind")
    heads = data.get("heads")
    if isinstance(heads, bool) or not isinstance(heads, int) or not 0 < heads < 10 ** 7:
        raise StockError("Nombre de têtes positif attendu.", "heads")
    if kind == "opening":
        fy = _fy_of(on)
        if fy is None:
            raise StockError("Aucun exercice ne couvre cette date.", "on")
        if _previous_count(lot, fy) is not None:
            raise StockError("L'effectif d'ouverture vient de l'inventaire de la clôture précédente.", "kind", 409)
        if any(m.kind == "opening" and fy.start_date <= m.on <= fy.end_date for m in lot.movements):
            raise StockError("Effectif d'ouverture déjà saisi pour cet exercice.", "kind", 409)
    movement = StockLotMovement(lot=lot, on=on, kind=kind, heads=heads, note=_text(data.get("note"), 300))
    if data.get("purchase_line_id") is not None:
        if kind != "purchase" or db.session.get(PurchaseLine, data["purchase_line_id"]) is None:
            raise StockError("Ligne d'achat introuvable (mouvement d'achat seulement).", "purchase_line_id")
        movement.purchase_line_id = data["purchase_line_id"]
    if data.get("sale_id") is not None:
        if kind != "sale" or db.session.get(Sale, data["sale_id"]) is None:
            raise StockError("Vente introuvable (mouvement de vente seulement).", "sale_id")
        movement.sale_id = data["sale_id"]
    db.session.add(movement)
    if kind == "transfer_out":
        other = db.session.get(StockLot, data.get("counterpart_lot_id")) if isinstance(data.get("counterpart_lot_id"), int) else None
        if other is None or other.id == lot.id:
            raise StockError("Lot d'arrivée à choisir (autre que le lot de départ).", "counterpart_lot_id")
        movement.counterpart_lot = other
        db.session.flush()
        movement.pair_id = movement.id
        db.session.add(StockLotMovement(lot=other, on=on, kind="transfer_in", heads=heads, counterpart_lot=lot,
                                        pair_id=movement.id, note=movement.note))
    db.session.flush()
    return movement


def delete_movement(lot: StockLot, movement: StockLotMovement) -> None:
    if movement.lot_id != lot.id:
        raise StockError("Mouvement introuvable.", status=404)
    _open_on(movement.on)
    if movement.asset_id is not None:                    # lot AG5.b : fiche immobilisée créée par le mouvement
        from app.services.assets import AssetError
        from app.services.living_assets import undo_from_stock
        try:
            undo_from_stock(movement)
        except AssetError as exc:
            raise StockError(str(exc), status=409) from None
    if movement.pair_id is not None:
        for row in StockLotMovement.query.filter_by(pair_id=movement.pair_id).all():
            db.session.delete(row)
    else:
        db.session.delete(movement)
    db.session.flush()


# ------------------------------------------------------------------ effectifs

def _previous_count(lot: StockLot, fy: FiscalYear) -> int | None:
    previous = previous_fiscal_year(fy)
    if previous is None:
        return None
    line = StockLine.query.filter_by(fiscal_year_id=previous.id, lot_id=lot.id).first()
    return line.heads if line is not None and line.heads is not None else None


def summary(lot: StockLot, fy: FiscalYear) -> dict:
    """Effectifs du lot sur l'exercice : ouverture, entrées et sorties par type, théorique, compté, écart."""
    previous = _previous_count(lot, fy)
    rows = [m for m in lot.movements if fy.start_date <= m.on <= fy.end_date]
    opening = previous if previous is not None else sum(m.heads for m in rows if m.kind == "opening")
    by_kind = {k: sum(m.heads for m in rows if m.kind == k) for k in (*LOT_IN, *LOT_OUT)}
    theoretical = opening + sum(by_kind[k] for k in LOT_IN) - sum(by_kind[k] for k in LOT_OUT)
    line = StockLine.query.filter_by(fiscal_year_id=fy.id, lot_id=lot.id).first()
    counted = line.heads if line is not None else None
    return {"opening": opening, "opening_source": "previous" if previous is not None else "movement",
            "movements": by_kind, "entries": sum(by_kind[k] for k in LOT_IN), "exits": sum(by_kind[k] for k in LOT_OUT),
            "theoretical": theoretical, "counted": counted, "gap": None if counted is None else counted - theoretical,
            "line_id": line.id if line is not None else None}


def lot_payload(lot: StockLot, fy: FiscalYear | None = None, with_movements: bool = False) -> dict:
    data = {"id": lot.id, "label": lot.label, "species": lot.species, "age_class": lot.age_class,
            "destination": lot.destination, "destination_label": LOT_DESTINATIONS[lot.destination],
            "account": {"id": lot.account_id, "code": lot.account.code, "label": lot.account.label},
            "average_weight_kg": str(lot.average_weight_kg) if lot.average_weight_kg is not None else None,
            "active": lot.active}
    if fy is not None:
        data["summary"] = summary(lot, fy)
        if with_movements:
            data["movements"] = [movement_payload(m) for m in lot.movements if fy.start_date <= m.on <= fy.end_date]
    return data


def movement_payload(m: StockLotMovement) -> dict:
    return {"id": m.id, "on": m.on.isoformat(), "kind": m.kind, "kind_label": LOT_MOVEMENTS[m.kind], "heads": m.heads,
            "sign": 1 if m.kind in LOT_IN or m.kind == "opening" else -1, "note": m.note,
            "counterpart": {"id": m.counterpart_lot.id, "label": m.counterpart_lot.label} if m.counterpart_lot else None,
            "purchase_line_id": m.purchase_line_id, "sale_id": m.sale_id, "paired": m.pair_id is not None,
            "asset": {"id": m.asset.id, "label": m.asset.label} if m.asset else None}


def lots_overview(fy: FiscalYear) -> list[dict]:
    return [lot_payload(lot, fy) for lot in StockLot.query.order_by(StockLot.active.desc(), StockLot.label)
            if lot.active or lot.movements]


# ------------------------------------------------------------------ contrôles des biens vivants (lot AG5.d)

BREEDER_WORDS = ("truie", "verrat", "taureau", "belier", "bouc", "etalon", "pouliniere", "vache allaitante",
                 "reproduct", "geniteur")


def _plain(text: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()


def breeders_in_stock_allowed(on: date) -> bool:
    """Option du profil fiscal « reproducteurs maintenus en stock » en vigueur (AGD22, Q-B6)."""
    from app.models import TaxOption
    return any(o.start_date <= on and (o.renounced_on is None or on < o.renounced_on)
               for o in TaxOption.query.filter_by(code="breeders_in_stock"))


def looks_like_breeder(line: StockLine) -> bool:
    """Ligne d'animaux en stock qui ressemble à un reproducteur : lot de renouvellement ou libellé évocateur."""
    if line.category not in ANIMAL_CATEGORIES:
        return False
    if line.lot is not None and line.lot.destination == "breeding":
        return True
    text = _plain(f"{line.label} {line.production or ''} {line.lot.label if line.lot else ''}")
    return any(word in text for word in BREEDER_WORDS)


def breeder_warning(line: StockLine, fy: FiscalYear) -> str | None:
    if not looks_like_breeder(line) or breeders_in_stock_allowed(fy.end_date):
        return None
    return ("Reproducteur en stock : un animal qui restera durablement (plus de 12 mois) comme moyen de production "
            "s'immobilise (PCG 618-10) ; sinon, enregistrez l'option « reproducteurs maintenus en stock ».")


def checks(fy: FiscalYear) -> list[tuple[str, str, int, str]]:
    from app.services import stock_inventory
    if not stock_inventory.enabled():
        return []
    out = []
    breeders = [l for l in StockLine.query.filter_by(fiscal_year_id=fy.id) if breeder_warning(l, fy)]
    if breeders:
        out.append(("stock_breeders", "Reproducteurs en stock : à immobiliser s'ils restent durablement (ou option du "
                    "profil fiscal)", len(breeders), "info"))
    orphans = (StockLotMovement.query.filter(StockLotMovement.kind == "to_fixed_assets", StockLotMovement.asset_id.is_(None),
                                             StockLotMovement.on.between(fy.start_date, fy.end_date)).count())
    if orphans:
        out.append(("stock_to_assets_orphan", "Sorties de lots d'animaux vers les immobilisations sans fiche immobilisée "
                    "(utilisez « Vers les immobilisations »)", orphans, "info"))
    return out
