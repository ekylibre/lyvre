"""Remboursement forfaitaire agricole, 3520 (lot AG2.e, claudedocs/design_tva_agricole.md § 6).

Une exploitation au remboursement forfaitaire (`vat_regime = rfa`) ne collecte ni ne déduit la TVA ; elle demande,
l'année suivante, un forfait sur ses ventes de l'année civile à des clients assujettis.

- **Recettes** : lignes des comptes 70 de l'année civile (crédit − débit), hors à-nouveaux, clôture, inventaire et
  liquidations. En comptabilité simplifiée ce sont des encaissements ; en partie double, des ventes comptabilisées
  (un avertissement le rappelle : factures non encaissées au 31/12, encaissements de factures antérieures).
- **Classe de taux** d'un compte : celle de la catégorie de recettes (`simple_categories.rfa_rate`), sinon celle des
  produits du catalogue vendus sur ce compte s'ils sont d'accord (`products.rfa_rate`), sinon la proposition de la
  catégorie agricole (`CATEGORY_DEFAULTS`). `high` (5,59 %), `low` (4,43 %), `excluded`.
- **Client** : `entities.rfa_buyer`, sinon déduit de la fiche (régime de TVA, SIREN, numéro de TVA). Seuls les clients
  `professional`, `eu` et `export` ouvrent droit au forfait ; les particuliers (`none`) en sont exclus.
- **Forfait** : bases des classes `high` et `low` × taux (paramètres `vat.rfa.rate_high_bp`, `vat.rfa.rate_low_bp`
  de l'année des ventes), arrondi à l'euro.
- **Contrôles** : attestation d'achats manquante (client assujetti en France) ou écart de plus de 1 % ; vente sans
  classe de taux ; ventes sans client ; seuil de 46 000 € (moyenne des deux années civiles, × associés d'un GAEC).
- **Dépôt** : demande figée (`rfa_claims`) ; en partie double, écriture débit 44583, crédit 741. Échéance : 31/12/N+1.
"""
from __future__ import annotations

import json
from datetime import date

from app.extensions import db
from app.models import (
    Account, Associate, Entity, JournalEntry, JournalLine, Organization, Product, RfaAttestation, RfaClaim,
    SimpleCategory,
)
from app.models.journal_entry import SOURCE_VAT_RETURN
from app.services import reg_params, vat_codes
from app.services.vat_books import EXCLUDED_SOURCES

RATES = {"high": "Taux de 5,59 % (lait, œufs, volailles, animaux de boucherie, céréales, oléo-protéagineux)",
         "low": "Taux de 4,43 % (autres produits agricoles)",
         "excluded": "Exclu (produits transformés, prestations, ventes par moyens commerciaux)"}
BUYERS = {"professional": "Assujetti en France (attestation d'achats)", "eu": "Assujetti de l'UE (livraison intracommunautaire)",
          "export": "Exportation hors UE", "none": "Particulier ou non assujetti (exclu)"}
ELIGIBLE = ("professional", "eu", "export")
CATEGORY_DEFAULTS = {"ventes_produits_animaux": "high", "ventes_animaux": "high", "ventes_transformes": "excluded",
                     "travaux_facon": "excluded", "entraide": "excluded"}
ATTESTATION_TOLERANCE_BP = 100   # écart toléré entre l'attestation et les ventes de Lyvre (1 %)
REFUND_ACCOUNT = "44583"
INCOME_ACCOUNT = "741"


class RfaError(Exception):
    def __init__(self, message, field=None, status=409, problems=None):
        super().__init__(message)
        self.message, self.field, self.status, self.problems = message, field, status, problems or []


def _euro(cents: float) -> int:
    """Arrondi à l'euro le plus proche, en centimes."""
    return int((cents + 50) // 100) * 100 if cents >= 0 else -int((-cents + 50) // 100) * 100


# ------------------------------------------------------------------ classes de taux et clients

def guess_buyer(entity: Entity | None) -> str | None:
    if entity is None:
        return None
    if entity.vat_regime == "eu":
        return "eu"
    if entity.vat_regime == "world":
        return "export"
    if entity.siren or entity.siret or entity.vat_number or entity.person_kind == "company":
        return "professional"
    return "none"


def buyer_of(entity: Entity | None) -> tuple[str | None, bool]:
    """(type de client, deviné ?)."""
    if entity is not None and entity.rfa_buyer:
        return entity.rfa_buyer, False
    return guess_buyer(entity), True


def account_rates() -> dict[int, dict]:
    """Classe de taux de chaque compte de vente : {account_id: {rate, source}}."""
    out: dict[int, dict] = {}
    categories = SimpleCategory.query.filter_by(kind="income").all()
    for category in categories:
        if category.rfa_rate:
            out[category.account_id] = {"rate": category.rfa_rate, "source": "category", "label": category.label}
    by_account: dict[int, set] = {}
    for product in Product.query.filter(Product.sale_account_id.isnot(None), Product.rfa_rate.isnot(None)):
        by_account.setdefault(product.sale_account_id, set()).add(product.rfa_rate)
    for account_id, rates in by_account.items():
        if account_id not in out and len(rates) == 1:
            out[account_id] = {"rate": next(iter(rates)), "source": "products", "label": None}
    for category in categories:
        default = CATEGORY_DEFAULTS.get(category.code)
        if default and category.account_id not in out:
            out[category.account_id] = {"rate": default, "source": "proposed", "label": category.label}
    return out


# ------------------------------------------------------------------ recettes de l'année

def _sales_lines(year: int):
    """(ligne, compte, entité) des comptes 70 de l'année civile ; entité de la ligne, sinon l'unique tiers de la pièce."""
    start, end = date(year, 1, 1), date(year, 12, 31)
    lines = (db.session.query(JournalLine, Account)
             .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
             .join(Account, Account.id == JournalLine.account_id)
             .filter(Account.code.like("70%"), JournalEntry.entry_date.between(start, end),
                     db.or_(JournalEntry.source.is_(None), JournalEntry.source.notin_(EXCLUDED_SOURCES)))
             .order_by(JournalEntry.entry_date, JournalLine.id).all())
    entry_ids = {line.entry_id for line, _ in lines}
    tiers: dict[int, set] = {}
    if entry_ids:
        for entry_id, entity_id in (db.session.query(JournalLine.entry_id, JournalLine.entity_id)
                                    .filter(JournalLine.entry_id.in_(entry_ids), JournalLine.entity_id.isnot(None))):
            tiers.setdefault(entry_id, set()).add(entity_id)
    for line, account in lines:
        found = tiers.get(line.entry_id, set())
        entity_id = line.entity_id or (next(iter(found)) if len(found) == 1 else None)
        yield line, account, entity_id


def total_receipts(year: int) -> int:
    return sum(line.credit_cents - line.debit_cents for line, _, _ in _sales_lines(year))


def _associates_factor() -> int:
    org = Organization.query.first()
    if org is not None and org.legal_form_code == "GAEC":
        return max(Associate.query.count(), 1)
    return 1


def flat_amount(high_cents: int, low_cents: int, high_bp: int, low_bp: int) -> int:
    """Forfait : bases des deux classes × leurs taux, arrondi à l'euro. Règle unique (calculette 24, lot AG12.b)."""
    return _euro(high_cents * high_bp / 10000 + low_cents * low_bp / 10000)


def compute(year: int, today: date | None = None) -> dict:
    """Demande de l'année des ventes `year` : clients, bases par classe, forfait, contrôles, seuil."""
    from app.services import tax_profile
    from app.tenant import current_instance

    today = today or date.today()
    on = date(year, 12, 31)
    rates = account_rates()
    clients: dict[int | None, dict] = {}
    accounts: dict[int, dict] = {}
    for line, account, entity_id in _sales_lines(year):
        amount = line.credit_cents - line.debit_cents
        rate = (rates.get(account.id) or {}).get("rate")
        client = clients.setdefault(entity_id, {"high": 0, "low": 0, "excluded": 0, "unclassified": 0})
        client[rate or "unclassified"] += amount
        row = accounts.setdefault(account.id, {"account_id": account.id, "code": account.code, "label": account.label,
                                               "rate": rate, "source": (rates.get(account.id) or {}).get("source"),
                                               "total_cents": 0})
        row["total_cents"] += amount
    entities = {e.id: e for e in Entity.query.filter(Entity.id.in_([i for i in clients if i]))} if clients else {}
    attestations = {a.entity_id: a for a in RfaAttestation.query.filter_by(year=year)}
    out_clients, problems, warnings = [], [], []
    bases = {"high": 0, "low": 0}
    excluded_cents = non_eligible_cents = unclassified_cents = 0
    for entity_id, amounts in clients.items():
        entity = entities.get(entity_id)
        buyer, guessed = buyer_of(entity)
        eligible = buyer in ELIGIBLE
        eligible_cents = amounts["high"] + amounts["low"] if eligible else 0
        if eligible:
            bases["high"] += amounts["high"]
            bases["low"] += amounts["low"]
            unclassified_cents += amounts["unclassified"]
        else:
            non_eligible_cents += amounts["high"] + amounts["low"] + amounts["unclassified"]
        excluded_cents += amounts["excluded"]
        attestation = attestations.get(entity_id)
        issues = []
        if entity is None:
            issues.append("Ventes sans client : rattachez un tiers aux recettes.")
        if eligible and amounts["unclassified"]:
            issues.append("Ventes sans classe de taux.")
        if buyer == "professional" and eligible_cents > 0:
            if attestation is None:
                issues.append("Attestation d'achats manquante.")
            elif abs(attestation.amount_cents - eligible_cents) * 10000 > ATTESTATION_TOLERANCE_BP * max(eligible_cents, 1):
                issues.append(f"Attestation de {attestation.amount_cents / 100:.2f} € différente des ventes de Lyvre "
                              f"({eligible_cents / 100:.2f} €).")
        out_clients.append({
            "entity_id": entity_id, "name": entity.name if entity else "Sans client", "buyer": buyer,
            "buyer_guessed": guessed, "eligible": eligible, "high_cents": amounts["high"], "low_cents": amounts["low"],
            "excluded_cents": amounts["excluded"], "unclassified_cents": amounts["unclassified"],
            "eligible_cents": eligible_cents, "attestation": attestation_payload(attestation), "issues": issues})
    out_clients.sort(key=lambda c: (not c["eligible"], c["name"].lower()))
    high_bp = reg_params.value("vat.rfa.rate_high_bp", on, default=None)
    low_bp = reg_params.value("vat.rfa.rate_low_bp", on, default=None)
    if high_bp is None or low_bp is None:
        problems.append(f"Taux du remboursement forfaitaire de {year} inconnus (Administration › Paramètres réglementaires).")
    if unclassified_cents:
        problems.append(f"{unclassified_cents / 100:.2f} € de ventes à des clients assujettis sans classe de taux : "
                        "choisissez la classe des comptes de vente.")
    amount = flat_amount(bases["high"], bases["low"], high_bp or 0, low_bp or 0)
    missing = [c for c in out_clients if any(i.startswith("Attestation") for i in c["issues"])]
    if missing:
        warnings.append(f"{len(missing)} client{'s' if len(missing) > 1 else ''} sans attestation d'achats conforme : "
                        "joignez les attestations à la demande.")
    if any(c["entity_id"] is None for c in out_clients):
        warnings.append("Des ventes n'ont pas de client : elles ne comptent pas dans le forfait.")
    regime = tax_profile.current_value("vat_regime", on)
    if regime != "rfa":
        warnings.append("Le profil fiscal n'indique pas le remboursement forfaitaire pour cette année "
                        "(Organisation › Profil fiscal).")
    inst = current_instance()
    if inst is not None and inst.bookkeeping == "double":
        warnings.append("Partie double : les recettes sont les ventes comptabilisées de l'année. Le forfait porte sur les "
                        "encaissements : retirez les factures non encaissées au 31/12, ajoutez les encaissements de "
                        "factures antérieures.")
    threshold = reg_params.value("vat.rfa.threshold_cents", on, default=None)
    factor = _associates_factor()
    years = [{"year": y, "receipts_cents": total_receipts(y)} for y in (year - 1, year)]
    known = [y["receipts_cents"] for y in years if y["receipts_cents"]]
    average = round(sum(known) / len(known)) if known else 0
    over = bool(threshold) and average > threshold * factor
    if over:
        warnings.append(f"Moyenne des recettes de {year - 1} et {year} au-dessus de {threshold * factor // 100} € : passage "
                        "obligatoire au régime simplifié agricole à compter du 1er janvier suivant (CGI art. 298 bis).")
    claim = RfaClaim.query.filter_by(year=year).first()
    deadline = date(year + 1, 12, 31)
    return {"year": year, "regime": regime, "clients": out_clients, "accounts": sorted(accounts.values(), key=lambda a: a["code"]),
            "high_base_cents": bases["high"], "low_base_cents": bases["low"], "excluded_cents": excluded_cents,
            "non_eligible_cents": non_eligible_cents, "unclassified_cents": unclassified_cents,
            "high_bp": high_bp, "low_bp": low_bp, "amount_cents": amount, "deadline": deadline,
            "late": claim is None and today > deadline, "can_declare": claim is None and today.year > year and not problems,
            "threshold": {"threshold_cents": threshold, "factor": factor, "years": years, "average_cents": average, "over": over},
            "problems": problems, "warnings": warnings, "claim": claim}


def attestation_payload(attestation: RfaAttestation | None) -> dict | None:
    if attestation is None:
        return None
    return {"id": attestation.id, "amount_cents": attestation.amount_cents,
            "received_on": attestation.received_on.isoformat() if attestation.received_on else None,
            "note": attestation.note, "has_file": bool(attestation.attachment_path),
            "file_name": attestation.attachment_name}


# ------------------------------------------------------------------ saisies

def _choice(value, allowed, field):
    if value in (None, ""):
        return None
    if value not in allowed:
        raise RfaError("Valeur inconnue.", field, status=422)
    return value


def set_buyer(entity: Entity, value) -> None:
    entity.rfa_buyer = _choice(value, BUYERS, "rfa_buyer")
    db.session.flush()


def set_account_rate(account_id: int, value) -> SimpleCategory:
    """Classe de taux d'un compte de vente, portée par sa catégorie de recettes (créée si besoin)."""
    rate = _choice(value, RATES, "rfa_rate")
    account = db.session.get(Account, account_id)
    if account is None or not (account.code or "").startswith("70"):
        raise RfaError("Compte de vente (70) introuvable.", "account_id", status=404)
    category = SimpleCategory.query.filter_by(kind="income", account_id=account.id).first()
    if category is None:
        category = SimpleCategory(code=f"rfa_{account.code}"[:30], label=account.label[:120], kind="income",
                                  account_id=account.id, active=False)
        db.session.add(category)
    category.rfa_rate = rate
    db.session.flush()
    return category


def save_attestation(entity: Entity, year: int, amount_cents, received_on=None, note=None, token=None) -> RfaAttestation:
    from app.services import attachments

    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents < 0:
        raise RfaError("Montant attesté en centimes, positif.", "amount_cents", status=422)
    if RfaClaim.query.filter_by(year=year).first() is not None:
        raise RfaError(f"La demande de {year} est déposée : ses attestations sont figées.")
    row = RfaAttestation.query.filter_by(entity_id=entity.id, year=year).first()
    if row is None:
        row = RfaAttestation(entity_id=entity.id, year=year, amount_cents=amount_cents)
        db.session.add(row)
    row.amount_cents, row.received_on = amount_cents, received_on
    row.note = (str(note or "").strip())[:300] or None
    db.session.flush()
    if token:
        try:
            attachments.store(row, token, folder="rfa", day=date(year, 12, 31))
        except attachments.AttachmentError as exc:
            raise RfaError(str(exc), "attachment", status=422) from None
    return row


def delete_attestation(row: RfaAttestation) -> None:
    from app.services import attachments

    if RfaClaim.query.filter_by(year=row.year).first() is not None:
        raise RfaError(f"La demande de {row.year} est déposée : ses attestations sont figées.")
    path = attachments.path_of(row)
    if path is not None:
        path.unlink(missing_ok=True)
    db.session.delete(row)
    db.session.flush()


# ------------------------------------------------------------------ dépôt

def declare(year: int, declared_on: date, user_id=None) -> RfaClaim:
    """Dépôt de la demande (sans commit) : bases figées ; en partie double, écriture 44583 / 741."""
    from app.services import vat_return as vr
    from app.services.ledger import post_entry
    from app.tenant import current_instance

    if RfaClaim.query.filter_by(year=year).first() is not None:
        raise RfaError(f"La demande de {year} est déjà déposée.")
    if not isinstance(declared_on, date) or declared_on < date(year + 1, 1, 1):
        raise RfaError(f"La demande de {year} se dépose à partir du 1er janvier {year + 1}.", "declared_on", status=422)
    data = compute(year, today=declared_on)
    if data["problems"]:
        raise RfaError(data["problems"][0], problems=data["problems"])
    if data["amount_cents"] <= 0:
        raise RfaError("Aucun forfait à demander : pas de vente éligible.")
    detail = {"high_bp": data["high_bp"], "low_bp": data["low_bp"], "excluded_cents": data["excluded_cents"],
              "non_eligible_cents": data["non_eligible_cents"],
              "clients": [{k: c[k] for k in ("entity_id", "name", "buyer", "high_cents", "low_cents", "eligible_cents")}
                          for c in data["clients"] if c["eligible"]]}
    claim = RfaClaim(year=year, status="declared", high_base_cents=data["high_base_cents"],
                     low_base_cents=data["low_base_cents"], amount_cents=data["amount_cents"],
                     detail_json=json.dumps(detail, ensure_ascii=False), declared_on=declared_on,
                     declared_by_user_id=user_id)
    db.session.add(claim)
    db.session.flush()
    inst = current_instance()
    if inst is not None and inst.bookkeeping == "double":
        fy = vr.fiscal_year_for(declared_on)
        if fy is None:
            raise RfaError("Aucun exercice ne couvre la date de dépôt : créez-le pour passer la créance.", "declared_on")
        income = Account.query.filter_by(code=INCOME_ACCOUNT, is_header=False).first()
        if income is None:
            income = Account(code=INCOME_ACCOUNT, label="Remboursement forfaitaire de TVA", account_type="REVENUE")
            db.session.add(income)
            db.session.flush()
        label = f"Remboursement forfaitaire agricole {year} (3520)"
        entry = post_entry(fy.id, vr._journal().id, declared_on, label, [
            {"account_id": vat_codes.account(REFUND_ACCOUNT).id, "label": label, "debit_cents": claim.amount_cents,
             "credit_cents": 0},
            {"account_id": income.id, "label": label, "debit_cents": 0, "credit_cents": claim.amount_cents}],
            source=SOURCE_VAT_RETURN, source_ref=f"RFA_CLAIM:{claim.id}", commit=False)
        claim.entry_id = entry.id
    db.session.flush()
    return claim


def cancel(claim: RfaClaim) -> None:
    """Annule une demande non remboursée : écriture supprimée (brouillard) ou contrepassée (sans commit)."""
    from app.services.ledger import delete_entries, post_entry

    if claim.status == "refunded":
        raise RfaError("Demande remboursée : elle ne s'annule plus.")
    entry = claim.entry
    if entry is not None:
        if entry.validation_number is None:
            (outcome,) = delete_entries([entry.id], allow_managed=True)
            if outcome["status"] != "ok":
                raise RfaError(outcome["message"])
        else:
            inverse = [{"account_id": l.account_id, "label": l.label, "debit_cents": l.credit_cents,
                        "credit_cents": l.debit_cents} for l in entry.lines]
            post_entry(entry.fiscal_year_id, entry.journal_id, entry.entry_date,
                       f"Annulation — remboursement forfaitaire {claim.year}", inverse,
                       source=SOURCE_VAT_RETURN, source_ref=f"RFA_CLAIM_CANCEL:{claim.id}", commit=False)
    db.session.delete(claim)
    db.session.flush()


def mark_refunded(claim: RfaClaim, refunded_on: date) -> None:
    if claim.status == "refunded":
        raise RfaError("Demande déjà marquée remboursée.")
    if not isinstance(refunded_on, date) or refunded_on < claim.declared_on:
        raise RfaError("Date de remboursement invalide (après le dépôt).", "refunded_on", status=422)
    claim.status, claim.refunded_on = "refunded", refunded_on
    db.session.flush()


def years(today: date | None = None) -> list[int]:
    """Années de ventes proposées : de la première année avec des écritures à l'année en cours."""
    today = today or date.today()
    first = db.session.query(db.func.min(JournalEntry.entry_date)).scalar()
    start = first.year if first else today.year
    return list(range(today.year, start - 1, -1))
