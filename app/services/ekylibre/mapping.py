"""Correspondances Ekylibre → Lyvre : comptes (plan SCI), journaux, tiers.

Comptes (design § 4.1) :
- compte d'un tiers 401… / 411… sur 11 chiffres → `401` / `411` + 3 derniers chiffres ;
- compte courant d'associé 4551xxxx → compte de l'associé (4551001, 4551002… par numéro croissant) ;
  4552xxxx → 4552 ;
- autres → zéros de droite retirés : compte Lyvre de ce code s'il existe et n'est pas un regroupement ;
  regroupement → sous-compte `<code>000` créé ; absent → créé sous le regroupement le plus proche ;
- comptes de TVA déductible 4456x des achats : absorbés dans la charge (EK3), leur correspondance
  reste calculée pour les autres journaux ; repris comme les autres comptes pour une structure
  assujettie (lot RE1, profil `standard`).

Tiers : noms rendus uniques (Q5 de la restauration) : « nom (ville) », sinon « nom (#n° Ekylibre) ».
"""
import json
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from app.services.ekylibre.data import EkyData

DATA_DIR = Path(__file__).resolve().parents[3] / "data"
CHART_FILE = DATA_DIR / "plan_comptable_sci.json"


def chart_file(chart: str) -> Path:
    """Plan comptable du référentiel visé (lot RE1)."""
    return DATA_DIR / f"plan_comptable_{chart}.json"

JOURNALS = {"BANQ": "BQ", "ACHA": "AC", "VENT": "VE", "ODGE": "OD", "IMMO": "OD", "RG": "AN"}
JOURNAL_LABELS = {"BQ": "Banque", "AC": "Achats", "VE": "Ventes", "OD": "Opérations diverses", "AN": "À-nouveaux",
                  "AS": "Associés"}
TIERS_PREFIXES = ("401", "411")


class Chart:
    """Plan comptable cible : code → (libellé, regroupement)."""

    def __init__(self, accounts: dict[str, tuple[str, bool]]):
        self.accounts = dict(accounts)

    @classmethod
    def from_file(cls, path=CHART_FILE) -> "Chart":
        rows = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls({r["code"]: (r["label"], bool(r["is_header"])) for r in rows})

    @classmethod
    def from_database(cls) -> "Chart":
        from app.models import Account
        return cls({a.code: (a.label, a.is_header) for a in Account.query.all()})

    def usable(self, code: str) -> bool:
        return code in self.accounts and not self.accounts[code][1]

    def parent_of(self, code: str) -> str | None:
        for length in range(len(code) - 1, 0, -1):
            if code[:length] in self.accounts:
                return code[:length]
        return None


@dataclass
class AccountTarget:
    eky_number: str
    eky_label: str
    code: str
    label: str
    action: str            # existing, create, associate, vat (absorbée dans les achats), reclass (stock, RE4)
    parent: str | None = None
    entity_id: str | None = None


def strip_zeros(number: str) -> str:
    stripped = number.rstrip("0")
    return stripped if len(stripped) >= 3 else number[:3]


def associate_codes(data: EkyData) -> dict[str, str]:
    """Comptes courants d'associés Ekylibre (4551…) → comptes Lyvre 4551001, 4551002… par numéro."""
    numbers = sorted({a["number"] for a in data.rows["accounts"] if a["number"].startswith("4551")})
    return {n: f"4551{i:03d}" for i, n in enumerate(numbers, start=1)}


# Lot RE4 : comptes de stock de l'ancien plan agricole d'Ekylibre (fr_pcga : 30 approvisionnements, 37 produits)
# ramenés au plan agricole de Lyvre (31 / 32 approvisionnements, 33 en-cours, 35 produits, 37 marchandises).
# Le préfixe le plus long l'emporte ; numéro sans ses zéros de fin.
STOCK_RECLASS = {
    "3011": "31111", "3012": "31112", "3013": "31113", "3014": "31114", "3015": "31115", "3016": "31116",
    "3017": "321", "3019": "321", "301": "3111",
    "3021": "3221", "3022": "3222", "3026": "322", "3027": "322", "302": "32",
    "351": "33111", "373": "35113", "374": "35511", "376": "35513",
    "71373": "71351", "71372": "71355", "71374": "71355", "71376": "71355",
}


def stock_reclass(number: str) -> str | None:
    code = strip_zeros(number)
    best = max((p for p in STOCK_RECLASS if code.startswith(p)), key=len, default=None)
    return STOCK_RECLASS[best] if best else None


def map_accounts(data: EkyData, chart: Chart, numbers: set[str], absorb_vat: bool = True,
                 reclass_stock: bool = False) -> dict[str, AccountTarget]:
    accounts = {a["number"]: a for a in data.rows["accounts"]}
    tiers = {}
    for entity in data.rows["entities"]:
        for key in ("supplier_account_id", "client_account_id"):
            number = data.account_number(entity.get(key))
            if number:
                tiers[number] = entity
    associates = associate_codes(data)
    targets, taken = {}, set(chart.accounts)
    for number in sorted(numbers):
        label = accounts[number]["name"] if number in accounts else number
        if number in associates:
            targets[number] = AccountTarget(number, label, associates[number], label, "associate")
            continue
        if number.startswith(TIERS_PREFIXES) and len(number) > 8:
            code = number[:3] + number[-3:]
            if code in taken and not chart.usable(code):
                code = number[:3] + number[3:].lstrip("0")
            entity = tiers.get(number)
            name = entity["full_name"] if entity else label
            action = "existing" if chart.usable(code) else "create"
            targets[number] = AccountTarget(number, label, code, name, action, chart.parent_of(code),
                                            entity["id"] if entity else None)
            taken.add(code)
            continue
        if absorb_vat and number.startswith("4456"):
            targets[number] = AccountTarget(number, label, strip_zeros(number), label, "vat", chart.parent_of(strip_zeros(number)))
            continue
        target_code = stock_reclass(number) if reclass_stock else None
        if target_code is not None and chart.usable(target_code):
            targets[number] = AccountTarget(number, label, target_code, chart.accounts[target_code][0], "reclass")
            taken.add(target_code)
            continue
        code = strip_zeros(number)
        if chart.usable(code):
            targets[number] = AccountTarget(number, label, code, chart.accounts[code][0], "existing")
        elif code in chart.accounts:  # regroupement : sous-compte
            sub = f"{code}000"
            targets[number] = AccountTarget(number, label, sub, label, "existing" if chart.usable(sub) else "create", code)
        else:
            targets[number] = AccountTarget(number, label, code, label, "create", chart.parent_of(code))
        taken.add(targets[number].code)
    return targets


def map_journal(code: str) -> str:
    if code.startswith("CC"):
        return "AS"
    return JOURNALS.get(code, "OD")


@dataclass
class EntityTarget:
    eky_id: str
    name: str
    entity_type: str
    person_kind: str
    siret: str | None
    vat_number: str | None
    iban: str | None
    address_line1: str | None
    postal_code: str | None
    city: str | None
    supplier_code: str | None
    customer_code: str | None
    original_name: str | None = None   # nom d'Ekylibre quand il a été rendu unique (Q5)


def _address(data: EkyData, entity_id: str) -> tuple[str | None, str | None, str | None]:
    addresses = [a for a in data.rows["entity_addresses"]
                 if a["entity_id"] == entity_id and a.get("canal") == "mail" and not a.get("deleted_at")]
    if not addresses:
        return None, None, None
    address = sorted(addresses, key=lambda a: a.get("by_default") != "t")[0]
    lines = [address.get(f"mail_line_{n}") for n in range(2, 7) if address.get(f"mail_line_{n}")]
    street = next((l for l in lines if not l[:5].isdigit()), None)
    city_line = next((l for l in lines if l[:5].isdigit()), None)
    postal, city = (city_line[:5], city_line[5:].strip()) if city_line else (None, None)
    return street, postal, city


def _key(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(folded.lower().split())


def dedupe_names(targets: dict[str, EntityTarget], numbers: dict[str, str] | None = None) -> list[tuple[str, str, str]]:
    """Rend les noms uniques (Q5) : « nom (ville) », puis « nom (#n°) » si la ville ne suffit pas.
    Retourne les renommages (id Ekylibre, ancien nom, nouveau nom)."""
    numbers = numbers or {}
    groups = defaultdict(list)
    for target in targets.values():
        groups[_key(target.name)].append(target)
    renamed = []
    for group in groups.values():
        if len(group) < 2:
            continue
        by_city = defaultdict(list)
        for target in group:
            by_city[_key(f"{target.name} ({target.city})") if target.city else None].append(target)
        for city_key, members in by_city.items():
            for target in members:
                old = target.name
                suffix = target.city if city_key is not None and len(members) == 1 else f"#{numbers.get(target.eky_id) or target.eky_id}"
                target.name = f"{old[:200 - len(suffix) - 3]} ({suffix})"
                target.original_name = old
                renamed.append((target.eky_id, old, target.name))
    return renamed


def map_entities(data: EkyData, accounts: dict[str, AccountTarget], dedupe: bool = False) -> dict[str, EntityTarget]:
    targets = {}
    for entity_id in sorted(data.entities_used(), key=int):
        entity = data.get("entities", entity_id)
        if entity is None:
            continue
        supplier = accounts.get(data.account_number(entity.get("supplier_account_id")) or "")
        customer = accounts.get(data.account_number(entity.get("client_account_id")) or "")
        kind = "FOURNISSEUR" if entity.get("supplier") == "t" else "CLIENT" if entity.get("client") == "t" else "AUTRE"
        street, postal, city = _address(data, entity_id)
        targets[entity_id] = EntityTarget(
            entity_id, (entity.get("full_name") or "").strip()[:200], kind,
            "individual" if entity.get("nature") == "contact" else "company",
            (entity.get("siret_number") or "").replace(" ", "")[:14] or None,
            (entity.get("vat_number") or "").replace(" ", "")[:30] or None,
            (entity.get("iban") or "").replace(" ", "")[:34] or None,
            street, postal, city,
            supplier.code if supplier else None, customer.code if customer else None)
    if dedupe:
        dedupe_names(targets, {i: (data.get("entities", i) or {}).get("number") for i in targets})
    return targets
