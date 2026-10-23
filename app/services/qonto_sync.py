"""Synchronisation Qonto → comptes et transactions bancaires.

Rattachement des comptes : un compte Qonto est lié à un `BankAccount`
(`qonto_account_id`), existant (même IBAN proposé d'office) ou créé avec son
compte comptable. Seuls les comptes rattachés sont synchronisés.

Transactions (`sync_bank_account`) : lecture par fenêtres de temps (mensuelles
au premier passage, incrémentale ensuite via `updated_at`), dédoublonnage par
l'identifiant Qonto (`fitid`), commit par page, règles appliquées aux nouvelles
transactions ; le curseur `qonto_synced_at` n'avance qu'après un succès complet.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.extensions import db
from app.models import BankAccount, BankTransaction, FiscalYear

PARIS = ZoneInfo("Europe/Paris")
# Qonto refuse page × per_page > 10 000 : au-delà de ce nombre de résultats, la fenêtre est coupée.
SPLIT_THRESHOLD = 9000
PER_PAGE = 100
# Marge sur le curseur incrémental (décalage d'horloge) ; sans risque grâce à l'idempotence.
CURSOR_OVERLAP = timedelta(minutes=10)


class QontoLinkError(ValueError):
    """Rattachement impossible (message affichable)."""


@dataclass(frozen=True)
class QontoAccountView:
    qonto_id: str
    name: str
    iban: str | None
    status: str
    main: bool
    balance_cents: int | None
    linked: BankAccount | None     # compte bancaire déjà rattaché
    proposed: BankAccount | None   # compte non rattaché de même IBAN

    @property
    def is_closed(self) -> bool:
        return self.status != "active"


def normalize_iban(iban) -> str | None:
    value = (iban or "").replace(" ", "").upper()
    return value or None


def default_sync_from(today=None) -> date:
    """Début de l'exercice ouvert qui contient aujourd'hui, sinon 1er janvier."""
    today = today or date.today()
    fy = (
        FiscalYear.query
        .filter(FiscalYear.start_date <= today, FiscalYear.end_date >= today,
                FiscalYear.closed.is_(False))
        .order_by(FiscalYear.start_date.desc())
        .first()
    )
    return fy.start_date if fy else date(today.year, 1, 1)


def list_accounts(qonto_accounts: list[dict]) -> list[QontoAccountView]:
    """Comptes Qonto (réponse de l'API) avec leur rattachement local."""
    bank_accounts = BankAccount.query.all()
    by_qonto_id = {ba.qonto_account_id: ba for ba in bank_accounts if ba.qonto_account_id}
    unlinked_by_iban = {
        normalize_iban(ba.iban): ba for ba in bank_accounts
        if not ba.qonto_account_id and normalize_iban(ba.iban)
    }
    views = []
    for acc in qonto_accounts:
        iban = normalize_iban(acc.get("iban"))
        linked = by_qonto_id.get(acc["id"])
        views.append(QontoAccountView(
            qonto_id=acc["id"],
            name=acc.get("name") or "Compte Qonto",
            iban=iban,
            status=acc.get("status") or "active",
            main=bool(acc.get("main")),
            balance_cents=acc.get("balance_cents"),
            linked=linked,
            proposed=None if linked else unlinked_by_iban.get(iban),
        ))
    return views


def link_account(qonto_account: dict, *, bank_account_id=None, label=None,
                 gl_account_id=None, sync_from=None) -> BankAccount:
    """Rattache un compte Qonto à un compte bancaire existant, ou en crée un."""
    qonto_id = qonto_account["id"]
    already = BankAccount.query.filter_by(qonto_account_id=qonto_id).first()
    if already is not None:
        raise QontoLinkError(f"Ce compte Qonto est déjà rattaché à « {already.label} ».")

    if bank_account_id:
        bank_account = db.session.get(BankAccount, bank_account_id)
        if bank_account is None:
            raise QontoLinkError("Compte bancaire introuvable.")
        if bank_account.qonto_account_id:
            raise QontoLinkError(f"« {bank_account.label} » est déjà rattaché à un autre compte Qonto.")
        if not bank_account.iban:
            bank_account.iban = normalize_iban(qonto_account.get("iban"))
    else:
        label = (label or "").strip() or f"Qonto — {qonto_account.get('name') or 'compte'}"
        if not gl_account_id:
            raise QontoLinkError("Choisissez le compte comptable (classe 512) du nouveau compte.")
        bank_account = BankAccount(
            label=label,
            iban=normalize_iban(qonto_account.get("iban")),
            account_id=gl_account_id,
        )
        db.session.add(bank_account)

    bank_account.qonto_account_id = qonto_id
    bank_account.qonto_sync_from = sync_from or default_sync_from()
    bank_account.qonto_synced_at = None
    db.session.commit()
    return bank_account


def unlink_account(bank_account: BankAccount) -> None:
    """Détache le compte Qonto ; les transactions déjà importées sont conservées."""
    bank_account.qonto_account_id = None
    bank_account.qonto_synced_at = None
    db.session.commit()


def set_sync_from(bank_account: BankAccount, sync_from: date) -> None:
    """Change la date de début. Si elle recule, la prochaine synchro repart de zéro
    (les transactions déjà importées ne sont pas dupliquées)."""
    if bank_account.qonto_sync_from and sync_from < bank_account.qonto_sync_from:
        bank_account.qonto_synced_at = None
    bank_account.qonto_sync_from = sync_from
    db.session.commit()


# --------------------------------------------------------------- transactions

def _parse_utc(value) -> datetime | None:
    """Horodatage ISO 8601 de Qonto → datetime naïf en UTC."""
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def paris_date(value) -> date | None:
    """Date bancaire française d'un horodatage UTC (23 h 30 UTC le 1er = 2 en été)."""
    parsed = _parse_utc(value)
    if parsed is None:
        return None
    return parsed.replace(tzinfo=timezone.utc).astimezone(PARIS).date()


def _paris_midnight_utc(day: date) -> datetime:
    """Minuit (heure de Paris) de `day`, exprimé en UTC naïf."""
    return datetime.combine(day, time.min, PARIS).astimezone(timezone.utc).replace(tzinfo=None)


def _label(tx: dict) -> str:
    label = (tx.get("label") or "").strip()
    reference = (tx.get("reference") or "").strip()
    if reference and reference != label:
        label = f"{label} — {reference}" if label else reference
    return label[:500]


def _fields(tx: dict) -> dict:
    """Champs mis à jour à chaque synchronisation (jamais montant, date, rapprochement…)."""
    counterparty = (tx.get("clean_counterparty_name") or tx.get("label") or "").strip()
    return {
        "label": _label(tx),
        "counterparty": counterparty[:200] or None,
        "raw_type": (tx.get("operation_type") or "")[:40] or None,
        "note": tx.get("note") or None,
        "attachment_count": len([i for i in (tx.get("attachment_ids") or []) if i]),
        "attachment_required": bool(tx.get("attachment_required")),
        "attachment_lost": bool(tx.get("attachment_lost")),
        "source_updated_at": _parse_utc(tx.get("updated_at")),
    }


def signed_amount(tx: dict) -> int:
    amount = abs(int(tx.get("amount_cents") or 0))
    return -amount if tx.get("side") == "debit" else amount


def _new_result() -> dict:
    return {"created": 0, "updated": 0, "unchanged": 0, "reversed": 0, "reversed_reconciled": 0,
            "skipped": 0, "conflicts": 0, "rules_matched": 0, "rules_posted": 0,
            "linked_entities": 0, "proposed_counterparties": 0, "settled": 0, "errors": []}


def upsert_transaction(bank_account: BankAccount, tx: dict, result: dict, created: list) -> None:
    """Crée, met à jour ou signale une transaction Qonto (sans commit)."""
    existing = BankTransaction.query.filter_by(
        bank_account_id=bank_account.id, fitid=tx["id"]
    ).first()
    status = tx.get("status")

    if status == "reversed":
        if existing is None:
            result["skipped"] += 1
        elif not existing.is_reversed:
            existing.is_reversed = True
            result["reversed"] += 1
            if existing.reconciled:
                result["reversed_reconciled"] += 1
        else:
            result["unchanged"] += 1
        return
    if status != "completed":
        result["skipped"] += 1
        return

    settled = paris_date(tx.get("settled_at"))
    if settled is None or (bank_account.qonto_sync_from and settled < bank_account.qonto_sync_from):
        result["skipped"] += 1
        return

    fields = _fields(tx)
    amount = signed_amount(tx)
    if existing is None:
        txn = BankTransaction(
            bank_account_id=bank_account.id, fitid=tx["id"], source="qonto",
            transaction_date=settled, amount_cents=amount, **fields,
        )
        db.session.add(txn)
        created.append(txn)
        result["created"] += 1
        return

    if existing.amount_cents != amount:
        result["conflicts"] += 1
        result["errors"].append(
            f"Montant modifié dans Qonto pour {tx.get('transaction_id') or tx['id']} : "
            f"{existing.amount_cents} → {amount} centimes (non repris)."
        )
    changed = False
    for key, value in fields.items():
        if getattr(existing, key) != value:
            setattr(existing, key, value)
            changed = True
    result["updated" if changed else "unchanged"] += 1


def _windows(bank_account: BankAccount, started: datetime):
    """Fenêtres (filtres) à lire : mensuelles au premier passage, incrémentale ensuite."""
    if bank_account.qonto_synced_at is None:
        day = bank_account.qonto_sync_from or default_sync_from()
        month = date(day.year, day.month, 1)
        while True:
            start = _paris_midnight_utc(max(month, day))
            if start >= started:  # date de début dans le futur : rien à lire
                return
            next_month = date(month.year + month.month // 12, month.month % 12 + 1, 1)
            end = min(_paris_midnight_utc(next_month), started)
            yield {"key": "settled", "start": start, "end": end, "statuses": ("completed",)}
            if end >= started:
                return
            month = next_month
    else:
        yield {"key": "updated", "start": bank_account.qonto_synced_at - CURSOR_OVERLAP,
               "end": started, "statuses": ("completed", "reversed")}


def _iter_pages(client, qonto_account_id, window):
    """Pages de la fenêtre ; coupée en deux tant qu'elle dépasse SPLIT_THRESHOLD résultats."""
    key, start, end = window["key"], window["start"], window["end"]
    filters = {"statuses": window["statuses"], f"{key}_from": start, f"{key}_to": end,
               "per_page": PER_PAGE}
    items, meta = client.list_transactions(qonto_account_id, page=1, **filters)
    if (meta.get("total_count") or 0) > SPLIT_THRESHOLD and end - start > timedelta(minutes=1):
        middle = start + (end - start) / 2
        yield from _iter_pages(client, qonto_account_id, {**window, "end": middle})
        yield from _iter_pages(client, qonto_account_id, {**window, "start": middle})
        return
    yield items, meta
    page = meta.get("next_page")
    while page:
        items, meta = client.list_transactions(qonto_account_id, page=page, **filters)
        yield items, meta
        page = meta.get("next_page")


def sync_bank_account(bank_account_id, client=None, progress_cb=None) -> dict:
    """Synchronise les transactions Qonto d'un compte bancaire rattaché."""
    from app.services import counterparties, purchase_settlement, qonto_client, rules_engine

    bank_account = db.session.get(BankAccount, bank_account_id)
    if bank_account is None or not bank_account.qonto_account_id:
        raise RuntimeError("Ce compte bancaire n'est pas rattaché à Qonto.")
    client = client or qonto_client.from_app_config()

    started = datetime.utcnow()
    result = _new_result()
    done = 0
    for window in _windows(bank_account, started):
        for items, meta in _iter_pages(client, bank_account.qonto_account_id, window):
            created: list[BankTransaction] = []
            for tx in items:
                upsert_transaction(bank_account, tx, result, created)
                done += 1
                if progress_cb:
                    progress_cb(done, None, f"{done} transaction(s) lue(s)…")
            # Commit puis règles par page : après un échec, les pages déjà validées ont
            # leurs règles appliquées et la reprise ne les recrée pas.
            db.session.commit()
            if created:
                # Transactions payant une facture d'achat : règlement 401 / banque, pas de règle
                # (apply_rules les ignore).
                purchase_settlement.link_transactions(created)
                db.session.commit()
                settlement = purchase_settlement.settle(transactions=created)
                result["settled"] += settlement["settled"]
                result["errors"].extend(settlement["errors"])
                # Crédit de même montant que le restant dû d'une seule facture de vente : encaissée.
                from app.services import sale_settlement
                sales = sale_settlement.auto_match()
                result["settled"] += sales["matched"]
                result["errors"].extend(sales["errors"])
                rules = rules_engine.apply_rules(created)
                result["rules_matched"] += rules["matched"]
                result["rules_posted"] += rules["posted"]
                result["errors"].extend(rules["errors"])
                # Après les règles : tiers existant de même nom pour celles restées sans tiers.
                result["linked_entities"] += counterparties.link_existing(created)

    result["proposed_counterparties"] = counterparties.count_proposals(bank_account.id)
    bank_account.qonto_synced_at = started
    db.session.commit()
    result["read"] = done
    return result


def start_sync(app, bank_account_id):
    """Lance (ou renvoie) la synchronisation en arrière-plan d'un compte."""
    from app.models.sync_job import SYNC_KIND_QONTO
    from app.services import integrations, sync_jobs

    def work(job_id):
        return sync_bank_account(bank_account_id,
                                 progress_cb=sync_jobs.progress_callback(job_id))

    def error_message(exc):
        if type(exc) is RuntimeError:  # message métier déjà rédigé
            return str(exc)
        return integrations.mask_secrets("qonto", integrations.describe_error("qonto", exc))

    return sync_jobs.start(
        app, SYNC_KIND_QONTO, work, bank_account_id=bank_account_id,
        message="Démarrage de la synchronisation Qonto…", error_message=error_message,
    )


def latest_job(bank_account_id):
    from app.models import SyncJob
    from app.models.sync_job import SYNC_KIND_QONTO

    return (
        SyncJob.query.filter_by(kind=SYNC_KIND_QONTO, bank_account_id=bank_account_id)
        .order_by(SyncJob.started_at.desc(), SyncJob.id.desc())
        .first()
    )
