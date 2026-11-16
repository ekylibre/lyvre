"""Catalogue d'une exploitation agricole (lot AG1.e, claudedocs/design_compta_agricole.md § 7.1) : les catégories
d'articles de `data/agri_purchase_categories.json` deviennent des articles du catalogue (compte d'achat et/ou de
vente du plan agri, taux de TVA par défaut). La saisie d'un achat ou d'une vente propose déjà le compte et le taux
de l'article choisi ; rien n'est imposé.

Idempotent : un article de même nom n'est ni recréé ni modifié (l'exploitant a pu l'adapter).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.extensions import db
from app.models import Account, Product

DATA = Path(__file__).resolve().parents[2] / "data" / "agri_purchase_categories.json"
# Ventes de produits agricoles : biens (exigibilité de la TVA à la livraison).
GOODS_PREFIXES = ("7011", "7012", "7013", "7014")


@lru_cache(maxsize=1)
def categories() -> tuple[dict, ...]:
    return tuple(json.loads(DATA.read_text(encoding="utf-8"))["categories"])


def _account(code: str | None) -> Account | None:
    if not code:
        return None
    return Account.query.filter_by(code=code, is_header=False).first()


def seed_catalog() -> dict:
    """Ajoute au catalogue les catégories absentes (par nom) ; renvoie le nombre d'articles créés et ignorés."""
    existing = {name for (name,) in db.session.query(Product.name)}
    created = skipped = 0
    for item in categories():
        if item["label"] in existing:
            skipped += 1
            continue
        purchase, sale = _account(item["purchase_account"]), _account(item["sale_account"])
        if purchase is None and sale is None:
            skipped += 1
            continue
        kind = "both" if purchase and sale else "sale" if sale else "purchase"
        db.session.add(Product(
            name=item["label"], kind=kind, purchase_account_id=purchase.id if purchase else None,
            sale_account_id=sale.id if sale else None, vat_rate_bp=item["vat_rate_bp"],
            nature="goods" if sale is not None and sale.code.startswith(GOODS_PREFIXES) else "services",
            description=None))
        created += 1
    db.session.commit()
    return {"created": created, "skipped": skipped}
