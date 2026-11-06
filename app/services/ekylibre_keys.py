"""Connecteur Ekylibre, lot AG11.c (claudedocs/design_connecteur_ekylibre.md § 4) : clés de répartition calculées
depuis les coûts des interventions.

Lu dans l'instantané local (interventions, cultures), jamais dans l'API :
- interventions **réalisées** (`nature = record`, état autre que `rejected`) commencées dans l'exercice ;
- chaque intervention est imputée à ses **cibles** : culture → activité Ekylibre → activité Lyvre (`ekylibre_id`,
  lot AG11.b). Plusieurs cibles : coût réparti **au prorata de leurs surfaces** (Q-K3). Une cible qui n'est pas une
  culture rattachée laisse sa part « non imputée » (affichée, hors clé) ;
- quatre clés, base `percentage`, parts = coûts de l'exercice ramenés à 10 000 points :
  intrants (`inputs`), main-d'œuvre (`doers`), matériel (`tools`) et heures de matériel (durée des interventions
  avec matériel). Les coûts de réception (`receptions`) ne font pas de clé.

Ce ne sont que des **poids** : les coûts d'Ekylibre (prix d'achat des intrants, taux horaires) ne sont pas
comptabilisés. Les clés sont refaites à chaque calcul (`source = ekylibre`, `synced_at`) ; les règles « compte →
clé » sont proposées, jamais imposées, et ne touchent pas une ligne déjà ventilée.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from app.extensions import db
from app.models import Activity, AnalyticKey, AnalyticRule, FiscalYear
from app.services import ekylibre_sync

FULL = 10000
KEYS = {
    "inputs": "Intrants (Ekylibre)",
    "doers": "Main-d'œuvre (Ekylibre)",
    "tools": "Matériel (Ekylibre)",
    "hours": "Heures de matériel (Ekylibre)",
}
UNITS = {"inputs": "€", "doers": "€", "tools": "€", "hours": "h"}
# Règles proposées : préfixe de compte → clé (design § 4). Proposées seulement si le préfixe n'a pas de règle.
RULES = (("601", "inputs", "Achats d'approvisionnements (engrais, semences, produits de défense)"),
         ("602", "inputs", "Autres approvisionnements"),
         ("6061", "tools", "Carburants et fournitures non stockables"),
         ("6155", "tools", "Entretien et réparations du matériel"),
         ("64", "doers", "Charges de personnel"))


class EkylibreKeyError(ValueError):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


def _shares(amounts: dict[int, Decimal]) -> dict[int, int]:
    """Parts en points de base, somme 10 000 (plus forts restes)."""
    total = sum(amounts.values())
    if total <= 0:
        return {}
    raw = {k: Decimal(v) * FULL / total for k, v in amounts.items()}
    shares = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: raw[k] - shares[k], reverse=True)[:FULL - sum(shares.values())]:
        shares[k] += 1
    return shares


def compute(fy: FiscalYear) -> dict:
    interventions, synced_at = ekylibre_sync.snapshot("interventions")
    productions, _ = ekylibre_sync.snapshot("productions")
    plants = {p.id: p for p in productions}
    linked = {a.ekylibre_id: a for a in Activity.query.filter(Activity.ekylibre_id.isnot(None), Activity.archived.is_(False))}
    amounts: dict[str, dict[int, Decimal]] = {kind: defaultdict(Decimal) for kind in KEYS}
    unassigned: dict[str, Decimal] = defaultdict(Decimal)
    used = skipped = 0
    for i in interventions:
        if i.nature != "record" or i.state == "rejected" or i.started_at is None:
            continue
        if not fy.start_date <= i.started_at.date() <= fy.end_date:
            continue
        used += 1
        values = {"inputs": i.costs.get("inputs", Decimal(0)), "doers": i.costs.get("doers", Decimal(0)),
                  "tools": i.costs.get("tools", Decimal(0)),
                  "hours": Decimal(i.working_seconds) / 3600 if i.tools else Decimal(0)}
        targets = [plants[t] for t in i.targets if t in plants and plants[t].surface_ha]
        surface = sum((p.surface_ha for p in targets), Decimal(0))
        if not targets or not surface:
            skipped += 1
            for kind, value in values.items():
                unassigned[kind] += value
            continue
        for plant in targets:
            ratio = plant.surface_ha / surface
            activity = linked.get(plant.activity_id)
            for kind, value in values.items():
                if activity is None:
                    unassigned[kind] += value * ratio
                else:
                    amounts[kind][activity.id] += value * ratio
    names = {a.id: a.name for a in linked.values()}
    keys = []
    for kind, label in KEYS.items():
        shares = _shares(amounts[kind])
        keys.append({"kind": kind, "name": label, "unit": UNITS[kind],
                     "total": str(sum(amounts[kind].values(), Decimal(0)).quantize(Decimal("0.01"))),
                     "unassigned": str(unassigned[kind].quantize(Decimal("0.01"))),
                     "members": [{"activity_id": aid, "activity": names[aid], "amount": str(v.quantize(Decimal("0.01"))),
                                  "share_bp": shares.get(aid, 0)}
                                 for aid, v in sorted(amounts[kind].items(), key=lambda x: -x[1]) if v > 0]})
    return {"fiscal_year": {"id": fy.id, "label": fy.label}, "synced_at": synced_at.isoformat() if synced_at else None,
            "interventions": used, "without_target": skipped, "keys": keys, "rules": proposed_rules()}


def apply(fy: FiscalYear) -> dict:
    """Crée ou refait les clés (base pourcentage) ; une clé sans montant n'est pas créée."""
    from app.services.analytic_allocation import save_key
    data = compute(fy)
    if not data["interventions"]:
        raise EkylibreKeyError("Aucune intervention réalisée de l'exercice dans la dernière lecture d'Ekylibre.", status=409)
    done = []
    for key in data["keys"]:
        members = [{"activity_id": m["activity_id"], "share_bp": m["share_bp"]} for m in key["members"] if m["share_bp"]]
        if not members:
            continue
        row = AnalyticKey.query.filter_by(name=key["name"]).first()
        if row is not None and row.source != "ekylibre":
            raise EkylibreKeyError(f"Une clé saisie porte déjà le nom « {key['name']} » : renommez-la.", status=409)
        row = save_key(row, {"name": key["name"], "basis": "percentage", "members": members, "archived": False,
                             "note": f"Calculée depuis Ekylibre (lecture du {data['synced_at'][:10]}) sur l'exercice "
                                     f"{fy.label} : {data['interventions']} intervention(s)."})
        row.source, row.synced_at = "ekylibre", datetime.utcnow()
        done.append(key["name"])
    db.session.commit()
    return {**compute(fy), "applied": done}


def proposed_rules() -> list[dict]:
    from app.models import Account
    existing = {r.account_prefix: r for r in AnalyticRule.query.all()}
    keys = {k.name: k for k in AnalyticKey.query.filter_by(source="ekylibre")}
    out = []
    for prefix, kind, label in RULES:
        if Account.query.filter(Account.code.like(f"{prefix}%")).first() is None:
            continue
        rule = existing.get(prefix)
        key = keys.get(KEYS[kind])
        out.append({"prefix": prefix, "label": label, "key": KEYS[kind], "key_id": key.id if key else None,
                    "existing": (rule.key.name if rule.key else rule.activity.name if rule.activity else "?") if rule else None})
    return out


def apply_rules(prefixes: list) -> int:
    from app.services.analytic_allocation import save_rule
    if not isinstance(prefixes, list) or not prefixes:
        raise EkylibreKeyError("Aucune règle choisie.", "prefixes")
    offered = {r["prefix"]: r for r in proposed_rules()}
    count = 0
    for prefix in prefixes:
        rule = offered.get(prefix)
        if rule is None or rule["existing"] is not None:
            raise EkylibreKeyError(f"Règle {prefix} non proposée (déjà une règle, ou compte absent).", "prefixes", 409)
        if rule["key_id"] is None:
            raise EkylibreKeyError(f"Calculez d'abord la clé « {rule['key']} ».", "prefixes", 409)
        save_rule({"account_prefix": prefix, "key_id": rule["key_id"]})
        count += 1
    db.session.commit()
    return count
