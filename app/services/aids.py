"""Registre des aides PAC et subventions (lot AG3.a, claudedocs/design_aides_pac.md §§ 2 à 4, décision AGD20).

- Dispositifs en données (`data/aids/schemes.yml`) : compte proposé, fait générateur, payeur, versements types.
- Dossier = une campagne d'un dispositif : montants demandé, notifié et versé, compte choisi (un sous-compte proposé
  absent du plan se crée sous son parent), dates limites. Les écritures restent celles de la banque ; le
  rattachement à l'exercice (AG3.c) et la reprise des subventions d'investissement (AG3.d) lisent ces dossiers.
- Versements saisis à la main (sans relevé) ; le rattachement des virements vient en AG3.b.
- « Nouvelle campagne PAC » : propose les dossiers d'après le profil de l'exploitation (PAC, JA, productions).
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml

from app.extensions import db
from app.models import Account, Aid, AidPayment, Entity
from app.models.aid import AID_NATURES, AID_PAYMENT_KINDS, AID_STATUSES, AID_TRIGGERS

DATA = Path(__file__).resolve().parents[2] / "data" / "aids" / "schemes.yml"
DEFAULT_PAC_KEY = "agenda.pac.deadline"
PAC_FALLBACK = (5, 15)                      # date limite habituelle, faute de paramètre de l'année
ACCOUNT_PREFIXES = {"operating": ("74",), "investment": ("13",), "mixed": ("13",)}
MAX_CENTS = 10 ** 11


class AidError(Exception):
    def __init__(self, message, field=None, status=422):
        super().__init__(message)
        self.message, self.field, self.status = message, field, status


# ------------------------------------------------------------------ dispositifs

def _check(items: list) -> None:
    keys = set()
    for item in items:
        key = item.get("key")
        where = f"dispositif {key!r}"
        if not key or key in keys:
            raise ValueError(f"{where} : clé absente ou en double")
        keys.add(key)
        if item.get("nature") not in AID_NATURES or item.get("trigger") not in AID_TRIGGERS:
            raise ValueError(f"{where} : nature ou fait générateur inconnu")
        account, parent = str(item.get("account") or ""), item.get("parent")
        if not account.startswith(ACCOUNT_PREFIXES[item["nature"]]):
            raise ValueError(f"{where} : compte {account} hors de {ACCOUNT_PREFIXES[item['nature']]}")
        if parent and not account.startswith(str(parent)):
            raise ValueError(f"{where} : {account} n'est pas sous {parent}")
        if item["nature"] == "mixed" and not str(item.get("operating_account") or "").startswith("74"):
            raise ValueError(f"{where} : aide mixte sans compte d'exploitation 74")
        for kind in item.get("payments") or []:
            if kind not in AID_PAYMENT_KINDS:
                raise ValueError(f"{where} : versement {kind!r} inconnu")


@lru_cache(maxsize=1)
def schemes() -> tuple[dict, ...]:
    items = yaml.safe_load(DATA.read_text(encoding="utf-8"))["schemes"]
    _check(items)
    return tuple(items)


def scheme(key: str) -> dict:
    for item in schemes():
        if item["key"] == key:
            return item
    raise AidError("Dispositif inconnu.", "scheme")


def _leaf(code: str) -> Account | None:
    return Account.query.filter_by(code=code, is_header=False).first() if code else None


def account_choices(item: dict) -> list[dict]:
    """Comptes proposés pour un dispositif : le sous-compte (à créer s'il manque) puis son parent."""
    out = []
    for code in dict.fromkeys(c for c in (str(item["account"]), str(item.get("parent") or "")) if c):
        account = Account.query.filter_by(code=code).first()
        if account is not None and account.is_header:
            continue
        out.append({"code": code, "label": account.label if account else f"{item['label']} (à créer)",
                    "exists": account is not None})
    return out


def scheme_payload(item: dict) -> dict:
    return {"key": item["key"], "label": item["label"], "pillar": item.get("pillar"), "nature": item["nature"],
            "trigger": item["trigger"], "payer": item.get("payer"), "payments": item.get("payments") or [],
            "accounts": account_choices(item), "operating_account": item.get("operating_account")}


def resolve_account(code: str, nature: str, item: dict | None, field: str = "account_code") -> Account:
    """Compte du dossier : existant (non en-tête, bonne classe), ou sous-compte proposé du dispositif, créé sous
    son parent."""
    code = str(code or "").strip()
    prefixes = ("74",) if field == "operating_account_code" else ACCOUNT_PREFIXES[nature]
    if not code.startswith(prefixes):
        raise AidError(f"Compte {' ou '.join(prefixes)}… attendu.", field)
    account = Account.query.filter_by(code=code).first()
    if account is not None:
        if account.is_header:
            raise AidError(f"« {code} » est un compte d'en-tête, non utilisable.", field)
        return account
    proposed = item and code == str(item["account"]) and item.get("parent")
    parent = _leaf(str(item["parent"])) if proposed else None
    if parent is None:
        raise AidError(f"Compte « {code} » introuvable dans le plan comptable.", field)
    account = Account(code=code, label=item["label"][:255], account_type=parent.account_type, parent_id=parent.id)
    db.session.add(account)
    db.session.flush()
    return account


# ------------------------------------------------------------------ montants et dates

def trigger_date(aid: Aid) -> tuple[date | None, bool]:
    """Date du fait générateur et « à confirmer » (date habituelle faute de paramètre de l'année)."""
    if aid.trigger == "decision":
        return aid.decision_on, False
    if aid.trigger == "payment":
        return None, False
    from app.services import reg_params

    key = DEFAULT_PAC_KEY
    try:
        key = scheme(aid.scheme).get("trigger_key") or key
    except AidError:
        pass
    param = reg_params.get(key, date(aid.campaign, 7, 1), default=None)
    values = param.value if param is not None else None
    if isinstance(values, list) and values:
        try:
            return date.fromisoformat(str(values[0])), False
        except ValueError:
            pass
    return date(aid.campaign, *PAC_FALLBACK), True


def acquired_cents(aid: Aid) -> int:
    """Montant acquis : notifié, sinon demandé (« estimé avec une fiabilité suffisante », PCG 618-6) ; rien pour
    un dossier refusé."""
    if aid.status == "refused":
        return 0
    return aid.notified_cents if aid.notified_cents is not None else (aid.requested_cents or 0)


def paid_cents(aid: Aid, until: date | None = None) -> int:
    return sum(p.amount_cents for p in aid.payments if until is None or p.paid_on <= until)


def _iso(value):
    return value.isoformat() if value else None


def _account_payload(account: Account | None) -> dict | None:
    return {"id": account.id, "code": account.code, "label": account.label} if account is not None else None


def payment_payload(payment: AidPayment) -> dict:
    tx = payment.bank_transaction
    return {"id": payment.id, "paid_on": _iso(payment.paid_on), "amount_cents": payment.amount_cents,
            "kind": payment.kind, "kind_label": AID_PAYMENT_KINDS.get(payment.kind, payment.kind), "note": payment.note,
            "bank_transaction": {"id": tx.id, "label": tx.label, "transaction_date": _iso(tx.transaction_date),
                                 "amount_cents": tx.amount_cents} if tx is not None else None}


def payload(aid: Aid, with_payments: bool = True) -> dict:
    when, provisional = trigger_date(aid)
    acquired, paid = acquired_cents(aid), paid_cents(aid)
    try:
        scheme_label = scheme(aid.scheme)["label"]
    except AidError:
        scheme_label = aid.scheme
    data = {
        "id": aid.id, "scheme": aid.scheme, "scheme_label": scheme_label, "label": aid.label, "campaign": aid.campaign,
        "payer": aid.payer, "funder": {"id": aid.funder.id, "name": aid.funder.name} if aid.funder else None,
        "nature": aid.nature, "nature_label": AID_NATURES[aid.nature],
        "account": _account_payload(aid.account), "operating_account": _account_payload(aid.operating_account),
        "investment_share_cents": aid.investment_share_cents,
        "trigger": aid.trigger, "trigger_label": AID_TRIGGERS[aid.trigger], "trigger_on": _iso(when),
        "trigger_provisional": provisional, "decision_on": _iso(aid.decision_on),
        "requested_cents": aid.requested_cents, "notified_cents": aid.notified_cents, "notified_on": _iso(aid.notified_on),
        "acquired_cents": acquired, "paid_cents": paid, "remaining_cents": acquired - paid,
        "payment_request_deadline": _iso(aid.payment_request_deadline),
        "payment_requested_on": _iso(aid.payment_requested_on), "commitment_end_on": _iso(aid.commitment_end_on),
        "status": aid.status, "status_label": AID_STATUSES[aid.status], "notes": aid.notes,
        "warnings": warnings(aid, acquired, paid),
    }
    if aid.nature in ("investment", "mixed"):
        from app.services import aid_grants
        grant_entry = aid.grant_entry
        data["investment"] = {
            "amount_cents": aid_grants.investment_cents(aid),
            "grant_entry": {"id": grant_entry.id, "reference": grant_entry.reference,
                            "entry_date": _iso(grant_entry.entry_date)} if grant_entry else None,
            "assets": [{"asset_id": link.asset_id, "label": link.asset.label, "amount_cents": link.amount_cents,
                        "method": link.asset.method, "status": link.asset.status} for link in aid.assets],
            "released_cents": sum(r.amount_cents for r in aid.releases if r.entry_id is not None),
        }
        data["warnings"] += aid_grants.warnings(aid)
    if with_payments:
        data["payments"] = [payment_payload(p) for p in aid.payments]
    return data


def warnings(aid: Aid, acquired: int | None = None, paid: int | None = None) -> list[str]:
    acquired = acquired_cents(aid) if acquired is None else acquired
    paid = paid_cents(aid) if paid is None else paid
    out = []
    if paid > acquired and aid.status != "refused":
        out.append("Versé au-delà du montant acquis : reversement à prévoir ou montant notifié à saisir.")
    if aid.status == "refused" and paid > 0:
        out.append("Dossier refusé mais versements enregistrés.")
    if aid.trigger == "decision" and aid.decision_on is None and aid.status != "refused":
        out.append("Date de la décision d'attribution à saisir (rattachement à l'exercice).")
    if aid.nature == "mixed" and aid.investment_share_cents is None:
        out.append("Ventilation à saisir : part d'investissement (131) et part d'exploitation.")
    if (aid.payment_request_deadline and not aid.payment_requested_on and aid.payment_request_deadline < date.today()
            and aid.status not in ("closed", "refused")):
        out.append("Date limite de la demande de paiement dépassée.")
    return out


def listing(campaign: int | None = None, status: str | None = None) -> list[Aid]:
    query = Aid.query
    if campaign is not None:
        query = query.filter_by(campaign=campaign)
    if status:
        query = query.filter_by(status=status)
    return query.order_by(Aid.campaign.desc(), Aid.id).all()


def campaigns() -> list[int]:
    years = {c for (c,) in db.session.query(Aid.campaign).distinct()}
    current = date.today().year
    return sorted(years | {current, current - 1}, reverse=True)


def totals(aids: list[Aid]) -> dict:
    out = {"requested_cents": 0, "acquired_cents": 0, "paid_cents": 0, "remaining_cents": 0}
    for aid in aids:
        acquired, paid = acquired_cents(aid), paid_cents(aid)
        out["requested_cents"] += aid.requested_cents or 0
        out["acquired_cents"] += acquired
        out["paid_cents"] += paid
        out["remaining_cents"] += acquired - paid
    return out


# ------------------------------------------------------------------ saisie

def _cents(value, field, label, allow_none=True, allow_negative=False):
    if value is None or value == "":
        if allow_none:
            return None
        raise AidError(f"{label} : montant attendu.", field)
    if isinstance(value, bool) or not isinstance(value, int):
        raise AidError(f"{label} : montant en centimes attendu.", field)
    if (value < 0 and not allow_negative) or abs(value) > MAX_CENTS:
        raise AidError(f"{label} : montant invalide.", field)
    return value


def _day(value, field, label):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        raise AidError(f"{label} : date attendue (AAAA-MM-JJ).", field) from None


def _text(value, limit):
    text = str(value or "").strip()
    return text[:limit] or None


DATES = {"decision_on": "Décision", "notified_on": "Notification", "payment_request_deadline": "Date limite de la demande de paiement",
         "payment_requested_on": "Demande de paiement", "commitment_end_on": "Fin d'engagement"}
AMOUNTS = {"requested_cents": "Montant demandé", "notified_cents": "Montant notifié",
           "investment_share_cents": "Part d'investissement"}
FIELDS = {"scheme", "label", "campaign", "payer", "funder_entity_id", "nature", "account_code", "operating_account_code",
          "trigger", "status", "notes", *DATES, *AMOUNTS}


def _apply(aid: Aid, data: dict, creating: bool) -> None:
    unknown = set(data) - FIELDS
    if unknown:
        raise AidError(f"Champ inconnu : {sorted(unknown)[0]}.", sorted(unknown)[0])
    if creating:
        item = scheme(str(data.get("scheme") or ""))
        aid.scheme = item["key"]
    else:
        if "scheme" in data and data["scheme"] != aid.scheme:
            raise AidError("Le dispositif d'un dossier ne se change pas : créez un autre dossier.", "scheme")
        try:
            item = scheme(aid.scheme)
        except AidError:
            item = None
    if "campaign" in data or creating:
        campaign = data.get("campaign")
        if isinstance(campaign, bool) or not isinstance(campaign, int) or not 2000 <= campaign <= 2100:
            raise AidError("Campagne : année attendue.", "campaign")
        aid.campaign = campaign
    if "label" in data or creating:
        aid.label = _text(data.get("label"), 200) or (item["label"] if item else aid.label)
    if creating:
        nature = data.get("nature") if aid.scheme == "other" and data.get("nature") else item["nature"]
        if nature not in AID_NATURES:
            raise AidError("Nature inconnue.", "nature")
        aid.nature = nature
        aid.trigger = item["trigger"]
        aid.payer = item.get("payer")
    if "trigger" in data:
        if data["trigger"] not in AID_TRIGGERS:
            raise AidError("Fait générateur inconnu.", "trigger")
        aid.trigger = data["trigger"]
    if "payer" in data:
        aid.payer = _text(data.get("payer"), 60)
    if "funder_entity_id" in data:
        entity_id = data["funder_entity_id"]
        if entity_id is not None and (not isinstance(entity_id, int) or db.session.get(Entity, entity_id) is None):
            raise AidError("Financeur introuvable.", "funder_entity_id")
        aid.funder_entity_id = entity_id
    if "account_code" in data or creating:
        code = data.get("account_code") or (str(item["account"]) if item else None)
        aid.account = resolve_account(code, aid.nature, item)
    if aid.nature == "mixed":
        if "operating_account_code" in data or creating:
            code = data.get("operating_account_code") or (item or {}).get("operating_account")
            aid.operating_account = resolve_account(code, aid.nature, item, "operating_account_code")
    elif data.get("operating_account_code"):
        raise AidError("Compte d'exploitation réservé aux aides mixtes.", "operating_account_code")
    for field, label in AMOUNTS.items():
        if field in data:
            setattr(aid, field, _cents(data[field], field, label))
    if aid.nature != "mixed":
        aid.investment_share_cents = None
    for field, label in DATES.items():
        if field in data:
            setattr(aid, field, _day(data[field], field, label))
    if "notes" in data:
        aid.notes = _text(data.get("notes"), 5000)
    if "status" in data:
        if data["status"] not in AID_STATUSES:
            raise AidError("Statut inconnu.", "status")
        aid.status = data["status"]
    elif aid.status == "requested" and aid.notified_cents is not None:
        aid.status = "granted"
    if aid.nature == "mixed" and aid.investment_share_cents is not None:
        total = acquired_cents(aid)
        if total and aid.investment_share_cents > total:
            raise AidError("La part d'investissement dépasse le montant de l'aide.", "investment_share_cents")


def create(data: dict) -> Aid:
    aid = Aid()
    _apply(aid, data, creating=True)
    db.session.add(aid)
    db.session.flush()
    return aid


def update(aid: Aid, data: dict) -> Aid:
    _apply(aid, data, creating=False)
    db.session.flush()
    return aid


def delete(aid: Aid) -> None:
    if any(p.bank_transaction_id for p in aid.payments):
        raise AidError("Des virements sont rattachés à ce dossier : détachez-les d'abord.", status=409)
    if aid.grant_entry_id is not None or any(r.entry_id for r in aid.releases):
        raise AidError("Un octroi ou une reprise est comptabilisé pour ce dossier : annulez-les d'abord.", status=409)
    if any(a.status == "posted" and a.journal_entry_id for a in aid.accruals):
        raise AidError("Une écriture de clôture (aide à recevoir) vient de ce dossier : supprimez-la d'abord depuis la "
                       "clôture de l'exercice.", status=409)
    db.session.delete(aid)
    db.session.flush()


def add_payment(aid: Aid, data: dict) -> AidPayment:
    unknown = set(data) - {"paid_on", "amount_cents", "kind", "note"}
    if unknown:
        raise AidError(f"Champ inconnu : {sorted(unknown)[0]}.", sorted(unknown)[0])
    paid_on = _day(data.get("paid_on"), "paid_on", "Date du versement")
    if paid_on is None:
        raise AidError("Date du versement : date attendue.", "paid_on")
    kind = data.get("kind") or "other"
    if kind not in AID_PAYMENT_KINDS:
        raise AidError("Type de versement inconnu.", "kind")
    amount = _cents(data.get("amount_cents"), "amount_cents", "Montant", allow_none=False, allow_negative=True)
    if amount == 0:
        raise AidError("Montant : non nul attendu.", "amount_cents")
    if (amount < 0) != (kind == "clawback"):
        raise AidError("Un reversement se saisit en négatif, un versement en positif.", "amount_cents")
    payment = AidPayment(aid=aid, paid_on=paid_on, amount_cents=amount, kind=kind, note=_text(data.get("note"), 300))
    db.session.add(payment)
    db.session.flush()
    return payment


def delete_payment(payment: AidPayment) -> None:
    db.session.delete(payment)
    db.session.flush()


# ------------------------------------------------------------------ campagne PAC

def _profile_match(when: dict, profile: dict) -> bool | None:
    from app.services import agri_profile

    flags = when.get("flags") or []
    productions = when.get("productions") or []
    if any(agri_profile.flag(profile, f) for f in flags):
        return True
    if any(p in (profile.get("productions") or []) for p in productions):
        return True
    return False


def pac_proposals(campaign: int) -> list[dict]:
    """Dossiers de la campagne PAC proposés d'après le profil : cochés d'office (dispositifs de base, conditions
    du profil remplies), à cocher sinon ; ceux qui existent déjà pour la campagne sont signalés."""
    from app.services import agri_profile

    profile = agri_profile.get()
    existing = {a.scheme for a in Aid.query.filter_by(campaign=campaign)}
    out = []
    for item in schemes():
        rule = item.get("campaign")
        if rule is None:
            continue
        if rule.get("default"):
            checked, reason = True, "dispositif de base"
        elif rule.get("when"):
            checked = bool(_profile_match(rule["when"], profile))
            reason = "selon le profil" if checked else None
        else:
            checked, reason = False, None
        out.append({"scheme": item["key"], "label": item["label"], "account": str(item["account"]),
                    "checked": checked and item["key"] not in existing, "reason": reason,
                    "exists": item["key"] in existing})
    return out


def create_pac_campaign(campaign: int, keys: list[str]) -> list[Aid]:
    if isinstance(campaign, bool) or not isinstance(campaign, int) or not 2000 <= campaign <= 2100:
        raise AidError("Campagne : année attendue.", "campaign")
    allowed = {p["scheme"]: p for p in pac_proposals(campaign)}
    if not isinstance(keys, list) or not keys:
        raise AidError("Cochez au moins un dispositif.", "schemes")
    created = []
    for key in dict.fromkeys(keys):
        if key not in allowed:
            raise AidError("Dispositif hors campagne PAC.", "schemes")
        if allowed[key]["exists"]:
            continue
        created.append(create({"scheme": key, "campaign": campaign}))
    return created
