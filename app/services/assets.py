"""Immobilisations et amortissements (lot F5), méthodes reprises d'Ekylibre (`FixedAsset`).

- **Jours (base 360)** : mois de 30 jours ; un 31 ou un dernier jour de mois compte pour 30
  (`days360`, = `FixedAsset.duration` d'Ekylibre).
- **Linéaire** : plan à partir de la mise en service, sur `durée × 30` jours ; la dotation d'un
  exercice = reste à amortir × jours de l'exercice / jours restants du plan (le reste exact la
  dernière année) : modifier la base ou la durée ne change que la suite du plan.
- **Dégressif** : plan à partir du 1er jour du mois d'acquisition ; taux = coefficient / années ;
  chaque exercice : reste × max(taux dégressif, 1 / années restantes) × jours / 360 (bascule en
  linéaire), le reste la dernière année.
- **Non amortissable** : terrain…
- Dotations passées (`asset_depreciations`) figées ; le plan se recalcule à partir d'elles.
- Écritures : mise en service (23x → 2x), dotations de l'exercice (une écriture OD gérée par
  l'assistant de clôture, source `DEPRECIATION`), sortie (cession ou rebut).
"""
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import Account, Asset, AssetDepreciation, FiscalYear, Journal, JournalEntry, Organization
from app.models.journal_entry import SOURCE_DEPRECIATION
from app.services import account_roles
from app.services.ledger_errors import LedgerError
from app.services.recurrence import add_months

COEFFICIENTS = ((48, Decimal("1.25")), (72, Decimal("1.75")), (10_000, Decimal("2.25")))  # durée ≤ … mois
METHOD_LABELS = {"linear": "Linéaire", "regressive": "Dégressif", "none": "Non amortissable"}
STATUS_LABELS = {"waiting": "En cours", "in_use": "En service", "depreciated": "Amortie", "sold": "Cédée",
                 "scrapped": "Mise au rebut"}


class AssetError(LedgerError):
    def __init__(self, message, field=None, status=409):
        super().__init__(message)
        self.field = field
        self.status = status


# ------------------------------------------------------------------ calendrier


def _thirty(day: date, start: bool, regressive: bool = False) -> int:
    last = (day + timedelta(days=1)).day == 1
    if day.day >= 30 or last:
        return 30
    if start and regressive:
        return 1
    return day.day


def days360(start: date, stop: date, regressive: bool = False) -> int:
    """Jours entre deux dates incluses, mois de 30 jours (Ekylibre `FixedAsset.duration`)."""
    if stop < start:
        return 0
    sa, so = _thirty(start, True, regressive), _thirty(stop, False)
    if (start.year, start.month) == (stop.year, stop.month):
        return so - sa + 1
    months = (stop.year - start.year) * 12 + stop.month - start.month - 1
    return 30 - sa + 1 + months * 30 + so


def default_coefficient(duration_months: int) -> Decimal:
    return next(coef for limit, coef in COEFFICIENTS if duration_months <= limit)


def plan_bounds(asset: Asset) -> tuple[date, date] | None:
    """(début, fin) du plan d'amortissement, ou None (non amortissable, en cours, sans durée)."""
    if asset.method == "none" or not asset.duration_months or asset.status == "waiting":
        return None
    if asset.method == "regressive":
        start = asset.acquired_on.replace(day=1)
    else:
        start = asset.in_service_date or asset.acquired_on
    return start, add_months(start, asset.duration_months, start.day) - timedelta(days=1)


def _anchor() -> tuple[int, int]:
    first = FiscalYear.query.order_by(FiscalYear.start_date).first()
    return (first.start_date.month, first.start_date.day) if first else (1, 1)


def periods(start: date, end: date) -> list[tuple[date, date, FiscalYear | None]]:
    """Exercices couvrant [start, end] : exercices existants, sinon années de même début."""
    years = FiscalYear.query.order_by(FiscalYear.start_date).all()
    month, day = _anchor()
    result, cursor = [], start
    while cursor <= end:
        fy = next((y for y in years if y.start_date <= cursor <= y.end_date), None)
        if fy is not None:
            result.append((fy.start_date, fy.end_date, fy))
            cursor = fy.end_date + timedelta(days=1)
            continue
        p_start = date(cursor.year, month, day)
        if p_start > cursor:
            p_start = date(cursor.year - 1, month, day)
        p_end = date(p_start.year + 1, month, day) - timedelta(days=1)
        following = next((y for y in years if y.start_date > cursor), None)
        if following is not None and following.start_date <= p_end:
            p_end = following.start_date - timedelta(days=1)
        result.append((p_start, p_end, None))
        cursor = p_end + timedelta(days=1)
    return result


@dataclass
class Row:
    fiscal_year_id: int | None
    label: str
    start: date
    stop: date
    days: int
    amount_cents: int
    cumulative_cents: int
    net_cents: int
    posted: bool


def schedule(asset: Asset, until: date | None = None) -> list[Row]:
    """Tableau d'amortissement : dotations passées, puis plan recalculé (`until` : sortie)."""
    bounds = plan_bounds(asset)
    if bounds is None:
        return []
    plan_start, plan_end = bounds
    stop_at = min(plan_end, until) if until else plan_end
    if asset.disposal_date and asset.status in ("sold", "scrapped"):
        stop_at = min(stop_at, asset.disposal_date)
    base = asset.base_cents
    already = asset.prior_depreciation_cents or 0
    begin = plan_start
    if asset.prior_as_of:
        begin = max(begin, asset.prior_as_of + timedelta(days=1))
    posted = {d.fiscal_year_id: d for d in asset.depreciations}
    regressive = asset.method == "regressive"
    years = Decimal(asset.duration_months) / 12
    coefficient = Decimal(asset.fiscal_coefficient or default_coefficient(asset.duration_months))
    rows, index = [], 0
    for p_start, p_end, fy in periods(plan_start, stop_at):
        if p_end < begin:
            index += 1
            continue
        seg_start, seg_stop = max(p_start, begin), min(p_end, stop_at)
        fy_days = days360(seg_start, seg_stop, regressive and index == 0)
        remaining = base - already
        record = posted.get(fy.id) if fy else None
        if record is not None:
            amount = record.amount_cents
        elif remaining <= 0:
            amount = 0
        elif seg_stop >= plan_end:
            amount = remaining
        elif regressive:
            rate = max(coefficient / years, 1 / max(years - index, Decimal(1)))
            amount = min(remaining, int((Decimal(remaining) * rate * fy_days / 360).quantize(Decimal(1), "ROUND_HALF_UP")))
        else:
            left = days360(seg_start, plan_end)
            amount = remaining if left <= fy_days else round(remaining * fy_days / left)
        already += amount
        label = fy.label if fy else f"{p_start.year}" if p_start.month == 1 else f"{p_start.year}-{p_end.year}"
        rows.append(Row(fy.id if fy else None, label, seg_start, seg_stop, fy_days, amount, already, asset.acquisition_cents - already,
                        record is not None))
        index += 1
        if already >= base:
            break
    return rows


def accumulated(asset: Asset, before: date | None = None) -> int:
    """Amortissements passés (reprise comprise), éventuellement avant une date."""
    total = asset.prior_depreciation_cents or 0
    for d in asset.depreciations:
        if before is None or d.stopped_on < before:
            total += d.amount_cents
    return total


# ------------------------------------------------------------------ comptes


def enabled() -> bool:
    """Amortissements comptabilisés : réglage de la structure, sinon oui pour une association."""
    org = Organization.query.first()
    if org is not None and org.depreciation_enabled is not None:
        return org.depreciation_enabled
    try:
        from app.tenant import current_chart, current_instance
        instance = current_instance()
        if instance is not None and getattr(instance, "bookkeeping", "double") == "simple":
            return False
        return current_chart() != "sci"  # SCI à l'IR : pas d'amortissement par défaut
    except RuntimeError:
        return True


def depreciation_account(account: Account) -> Account:
    """28 + suite du compte (2154 → 28154, sinon 2815, 281), créé s'il manque."""
    code = "28" + account.code[1:]
    for length in range(len(code), 2, -1):
        found = Account.query.filter_by(code=code[:length]).first()
        if found is not None and not found.is_header:
            return found
        if found is not None and found.is_header:
            parent = found
            break
    else:
        parent = Account.query.filter_by(code="28").first()
    created = Account(code=code, label=f"Amortissements — {account.label}"[:255], account_type="ASSET", parent=parent)
    db.session.add(created)
    db.session.flush()
    return created


def _role(role: str) -> Account:
    try:
        return account_roles.account_for(role)
    except account_roles.RoleError as exc:
        raise AssetError(str(exc)) from None


def _journal() -> Journal:
    journal = Journal.query.filter_by(code="OD").first()
    if journal is None:
        journal = Journal(code="OD", label="Opérations diverses")
        db.session.add(journal)
        db.session.flush()
    return journal


def _fy_for(on: date) -> FiscalYear:
    fy = FiscalYear.query.filter(FiscalYear.start_date <= on, FiscalYear.end_date >= on).first()
    if fy is None or fy.closed:
        raise AssetError(f"Aucun exercice ouvert au {on:%d/%m/%Y}.", "date")
    return fy


# ------------------------------------------------------------------ fiches


def leaves(asset: Asset) -> list[Asset]:
    return list(asset.components) if asset.components else [asset]


def save(asset: Asset | None, data: dict) -> Asset:
    """Crée ou modifie une fiche (sans commit). Base et durée ne changent plus le passé (dotations figées)."""
    from app.services.projects import resolve
    asset = asset or Asset()
    label = str(data.get("label") or "").strip()
    if not label:
        raise AssetError("Libellé obligatoire.", "label", 422)
    account = db.session.get(Account, data.get("account_id")) if isinstance(data.get("account_id"), int) else None
    if account is None or account.is_header or not account.code.startswith("2"):
        raise AssetError("Compte d'immobilisation (classe 2) obligatoire.", "account_id", 422)

    def day(key, required=False):
        value = data.get(key)
        if not value:
            if required:
                raise AssetError("Date obligatoire.", key, 422)
            return None
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            raise AssetError("Date invalide.", key, 422) from None

    def cents(key):
        value = data.get(key, 0)
        if value in (None, ""):
            return 0
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise AssetError("Montant invalide.", key, 422)
        return value

    method = data.get("method") or "linear"
    if method not in METHOD_LABELS:
        raise AssetError("Méthode inconnue.", "method", 422)
    duration = data.get("duration_months")
    if method != "none" and (not isinstance(duration, int) or isinstance(duration, bool) or not 1 <= duration <= 1200):
        raise AssetError("Durée en mois obligatoire (1 à 1200).", "duration_months", 422)
    asset.label = label[:200]
    asset.account_id = account.id
    asset.acquired_on = day("acquired_on", required=True)
    asset.in_service_date = day("in_service_date")
    asset.acquisition_cents = cents("acquisition_cents")
    asset.residual_cents = cents("residual_cents")
    if asset.residual_cents > asset.acquisition_cents:
        raise AssetError("Valeur résiduelle supérieure à la valeur d'origine.", "residual_cents", 422)
    asset.method = method
    asset.duration_months = duration if method != "none" else None
    coef = data.get("fiscal_coefficient")
    asset.fiscal_coefficient = Decimal(str(coef)) if method == "regressive" and coef else (
        default_coefficient(duration) if method == "regressive" else None)
    asset.prior_depreciation_cents = cents("prior_depreciation_cents")
    asset.prior_as_of = day("prior_as_of")
    if asset.prior_depreciation_cents and not asset.prior_as_of:
        raise AssetError("Date de la reprise obligatoire.", "prior_as_of", 422)
    try:
        project = resolve(data.get("project_id"))
    except ValueError as exc:
        raise AssetError(str(exc), "project_id", 422) from None
    asset.project_id = project.id if project else None
    asset.notes = (data.get("notes") or "").strip() or None
    if isinstance(data.get("parent_id"), int):
        parent = db.session.get(Asset, data["parent_id"])
        if parent is None or parent.parent_id is not None:
            raise AssetError("Bien parent introuvable.", "parent_id", 422)
        asset.parent_id = parent.id
    waiting = bool(data.get("waiting")) and not asset.in_service_date
    if asset.id is None:
        asset.status = "waiting" if waiting or account.code.startswith("23") else "in_use"
    if asset.status == "waiting":
        asset.waiting_account_id = account.id if account.code.startswith("23") else asset.waiting_account_id
    if method != "none" and asset.depreciation_account_id is None and not account.code.startswith("23"):
        asset.depreciation_account_id = depreciation_account(account).id
    db.session.add(asset)
    db.session.flush()
    return asset


def from_purchase_line(line) -> Asset:
    """Fiche préremplie depuis une ligne de facture d'achat au compte 2x / 23x (sans commit)."""
    purchase = line.purchase
    if line.account is None or not line.account.code.startswith("2"):
        raise AssetError("La ligne n'est pas sur un compte d'immobilisation.")
    if Asset.query.filter_by(purchase_line_id=line.id).first():
        raise AssetError("Immobilisation déjà créée pour cette ligne.")
    vat_liable = bool(purchase.journal_entry and purchase.journal_entry.fiscal_year.vat_liable)
    asset = save(None, {"label": line.label or purchase.invoice_number or "Immobilisation", "account_id": line.account_id,
                        "acquired_on": purchase.issue_date.isoformat(), "in_service_date": None
                        if line.account.code.startswith("23") else purchase.issue_date.isoformat(),
                        "acquisition_cents": line.untaxed_cents if vat_liable else line.total_cents,
                        "method": "linear", "duration_months": 60, "project_id": line.project_id})
    asset.purchase_line_id = line.id
    return asset


def put_in_service(asset: Asset, on: date, account_id: int | None = None, user_id=None) -> JournalEntry:
    """Immobilisation en cours mise en service : 2x au débit, 23x au crédit (sans commit)."""
    from app.services.ledger import post_entry
    if asset.status != "waiting":
        raise AssetError("Seule une immobilisation en cours se met en service.")
    target = db.session.get(Account, account_id) if account_id else asset.account
    if target is None or target.is_header or not target.code.startswith("2") or target.code.startswith("23"):
        raise AssetError("Compte d'immobilisation définitif (2x hors 23) obligatoire.", "account_id", 422)
    waiting = asset.waiting_account or asset.account
    fy = _fy_for(on)
    entry = post_entry(fy.id, _journal().id, on, f"Mise en service — {asset.label}"[:500], [
        {"account_id": target.id, "label": asset.label, "debit_cents": asset.acquisition_cents, "credit_cents": 0},
        {"account_id": waiting.id, "label": asset.label, "debit_cents": 0, "credit_cents": asset.acquisition_cents}],
        source="ASSET", commit=False)
    asset.waiting_account_id = waiting.id
    asset.account_id = target.id
    asset.in_service_date = on
    asset.status = "in_use"
    asset.in_service_entry_id = entry.id
    if asset.method != "none" and asset.depreciation_account_id is None:
        asset.depreciation_account_id = depreciation_account(target).id
    db.session.flush()
    return entry


# ------------------------------------------------------------------ dotations de l'exercice


def _depreciable(fy: FiscalYear):
    query = Asset.query.filter(Asset.method != "none", Asset.status.in_(("in_use", "depreciated")))
    return [a for a in query if not a.components]


def depreciation_rows(fy: FiscalYear) -> list[dict]:
    """Dotations de l'exercice par immobilisation (passées ou à passer)."""
    rows = []
    for asset in _depreciable(fy):
        row = next((r for r in schedule(asset) if r.fiscal_year_id == fy.id), None)
        if row is None or row.amount_cents <= 0:
            continue
        rows.append({"asset_id": asset.id, "label": asset.label, "account_code": asset.account.code,
                     "depreciation_account_code": asset.depreciation_account.code if asset.depreciation_account else None,
                     "start": row.start.isoformat(), "stop": row.stop.isoformat(), "days": row.days,
                     "amount_cents": row.amount_cents, "posted": row.posted})
    return rows


def depreciation_entry(fy: FiscalYear) -> JournalEntry | None:
    return JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_DEPRECIATION).first()


def cancel_depreciation(fy: FiscalYear) -> None:
    """Retire l'écriture de dotations de l'exercice et ses dotations (exercice ouvert, sans commit)."""
    from app.services.ledger import delete_entries
    entry = depreciation_entry(fy)
    if entry is None:
        return
    if fy.status != "open":
        raise AssetError("Exercice clôturé : les dotations sont figées.")
    if entry.is_validated:
        raise AssetError("Écriture de dotations validée : annulez d'abord son lot de validation.")
    AssetDepreciation.query.filter_by(fiscal_year_id=fy.id, entry_id=entry.id).delete()
    db.session.flush()
    (outcome,) = delete_entries([entry.id], allow_managed=True)
    if outcome["status"] != "ok":
        raise AssetError(outcome.get("message") or "Suppression impossible.")


def post_depreciation(fy: FiscalYear, user_id=None) -> JournalEntry | None:
    """Passe (ou repasse) les dotations de l'exercice : une écriture OD au dernier jour (commit)."""
    from app.services.ledger import post_entry
    from app.services.closing import log
    if fy.status != "open":
        raise AssetError("Exercice clôturé : rouvrez-le pour passer les dotations.")
    if not enabled():
        raise AssetError("Amortissements non comptabilisés pour cette structure (registre seulement).")
    cancel_depreciation(fy)
    db.session.expire_all()
    expense = _role("depreciation_expense")
    lines, records = [], []
    for asset in _depreciable(fy):
        row = next((r for r in schedule(asset) if r.fiscal_year_id == fy.id and not r.posted), None)
        if row is None or row.amount_cents <= 0:
            continue
        if asset.depreciation_account is None:
            asset.depreciation_account_id = depreciation_account(asset.account).id
            db.session.flush()
        target = asset.expense_account or expense
        lines += [{"account_id": target.id, "label": asset.label, "debit_cents": row.amount_cents, "credit_cents": 0,
                   "project_id": asset.project_id},
                  {"account_id": asset.depreciation_account_id, "label": asset.label, "debit_cents": 0,
                   "credit_cents": row.amount_cents}]
        records.append((asset, row))
    entry = None
    if lines:
        entry = post_entry(fy.id, _journal().id, fy.end_date, f"Dotations aux amortissements {fy.label}", lines,
                           source=SOURCE_DEPRECIATION, commit=False)
        for asset, row in records:
            db.session.add(AssetDepreciation(asset_id=asset.id, fiscal_year_id=fy.id, started_on=row.start,
                                             stopped_on=row.stop, days=row.days, amount_cents=row.amount_cents,
                                             entry_id=entry.id))
            if row.cumulative_cents >= asset.base_cents:
                asset.status = "depreciated"
    log(fy, "inventory", "depreciation", user_id, entry=entry.reference if entry else None, assets=len(records))
    db.session.commit()
    return entry


# ------------------------------------------------------------------ sortie


def dispose(asset: Asset, on: date, kind: str, price_cents: int = 0, sale_id: int | None = None, user_id=None) -> JournalEntry:
    """Cession (`sold`) ou mise au rebut (`scrapped`) à la date : dotation complémentaire, sortie de
    l'actif (2x / 28x / 675), prix de cession (462 / 775) sauf facture de vente rattachée (sans commit)."""
    from app.services.ledger import post_entry
    if kind not in ("sold", "scrapped"):
        raise AssetError("Type de sortie inconnu.", "kind", 422)
    if asset.status in ("sold", "scrapped") or asset.parent_id is not None and asset.parent.status in ("sold", "scrapped"):
        raise AssetError("Immobilisation déjà sortie.")
    if asset.status == "waiting":
        raise AssetError("Mettez d'abord l'immobilisation en service (ou supprimez la fiche).")
    fy = _fy_for(on)
    targets = leaves(asset)
    if any(d.fiscal_year_id == fy.id and d.entry_id and d.entry_id == getattr(depreciation_entry(fy), "id", None)
           for a in targets for d in a.depreciations):
        raise AssetError("Dotations de l'exercice déjà passées : annulez-les (assistant de clôture) avant la sortie.")
    expense = _role("depreciation_expense") if enabled() else None
    book_value = _role("disposal_book_value")
    lines, complements = [], []
    for leaf in targets:
        complement = 0
        if enabled() and leaf.method != "none":
            row = next((r for r in schedule(leaf, until=on) if r.fiscal_year_id == fy.id and not r.posted), None)
            complement = row.amount_cents if row else 0
            if complement:
                complements.append((leaf, row))
                lines += [{"account_id": (leaf.expense_account or expense).id, "label": leaf.label,
                           "debit_cents": complement, "credit_cents": 0, "project_id": leaf.project_id},
                          {"account_id": leaf.depreciation_account_id, "label": leaf.label, "debit_cents": 0,
                           "credit_cents": complement}]
        total = accumulated(leaf) + complement if enabled() else 0
        net = leaf.acquisition_cents - total
        if total:
            lines.append({"account_id": leaf.depreciation_account_id, "label": leaf.label, "debit_cents": total, "credit_cents": 0})
        if net:
            lines.append({"account_id": book_value.id, "label": leaf.label, "debit_cents": net, "credit_cents": 0})
        lines.append({"account_id": leaf.account_id, "label": leaf.label, "debit_cents": 0, "credit_cents": leaf.acquisition_cents})
    if kind == "sold" and price_cents and not sale_id:
        lines += [{"account_id": _role("disposal_receivable").id, "label": f"Cession — {asset.label}",
                   "debit_cents": price_cents, "credit_cents": 0},
                  {"account_id": _role("disposal_proceeds").id, "label": f"Cession — {asset.label}",
                   "debit_cents": 0, "credit_cents": price_cents}]
    text = ("Cession" if kind == "sold" else "Mise au rebut") + f" — {asset.label}"
    entry = post_entry(fy.id, _journal().id, on, text[:500], [l for l in lines if l["debit_cents"] or l["credit_cents"]],
                       source="ASSET", commit=False)
    for leaf, row in complements:
        db.session.add(AssetDepreciation(asset_id=leaf.id, fiscal_year_id=fy.id, started_on=row.start, stopped_on=row.stop,
                                         days=row.days, amount_cents=row.amount_cents, entry_id=entry.id))
    for item in {asset, *targets}:
        item.status, item.disposal_date = kind, on
    asset.disposal_price_cents = price_cents or None
    asset.sale_id = sale_id
    asset.disposal_entry_id = entry.id
    db.session.flush()
    return entry


# ------------------------------------------------------------------ états


def payload(asset: Asset, with_schedule: bool = False) -> dict:
    accum = sum(accumulated(leaf) for leaf in leaves(asset))
    data = {
        "id": asset.id, "parent_id": asset.parent_id, "label": asset.label,
        "account": {"id": asset.account.id, "code": asset.account.code, "label": asset.account.label},
        "depreciation_account_code": asset.depreciation_account.code if asset.depreciation_account else None,
        "acquired_on": asset.acquired_on.isoformat(),
        "in_service_date": asset.in_service_date.isoformat() if asset.in_service_date else None,
        "acquisition_cents": sum(l.acquisition_cents for l in leaves(asset)) if asset.components else asset.acquisition_cents,
        "residual_cents": asset.residual_cents, "method": asset.method, "method_label": METHOD_LABELS[asset.method],
        "duration_months": asset.duration_months,
        "fiscal_coefficient": str(asset.fiscal_coefficient) if asset.fiscal_coefficient else None,
        "prior_depreciation_cents": asset.prior_depreciation_cents,
        "prior_as_of": asset.prior_as_of.isoformat() if asset.prior_as_of else None,
        "project_id": asset.project_id, "project": asset.project.name if asset.project else None,
        "status": asset.status, "status_label": STATUS_LABELS[asset.status],
        "accumulated_cents": accum,
        "net_cents": (sum(l.acquisition_cents for l in leaves(asset)) if asset.components else asset.acquisition_cents) - accum,
        "disposal_date": asset.disposal_date.isoformat() if asset.disposal_date else None,
        "disposal_price_cents": asset.disposal_price_cents, "purchase_line_id": asset.purchase_line_id,
        "notes": asset.notes or "", "components": [payload(c) for c in asset.components],
        "deletable": not any(l.depreciations for l in leaves(asset)) and not asset.in_service_entry_id
        and not asset.disposal_entry_id,
    }
    if with_schedule:
        data["schedule"] = [{"fiscal_year_id": r.fiscal_year_id, "label": r.label, "start": r.start.isoformat(),
                             "stop": r.stop.isoformat(), "days": r.days, "amount_cents": r.amount_cents,
                             "cumulative_cents": r.cumulative_cents, "net_cents": r.net_cents, "posted": r.posted}
                            for r in schedule(asset)] if not asset.components else []
    return data


def annex(fy: FiscalYear) -> list[dict]:
    """Tableau des immobilisations et des amortissements de l'exercice, par compte (annexe)."""
    rows = {}
    for asset in Asset.query.all():
        if asset.components:
            continue
        code = asset.account.code
        row = rows.setdefault(code, {"account_code": code, "label": asset.account.label, "gross_start": 0, "increases": 0,
                                     "decreases": 0, "gross_end": 0, "depr_start": 0, "dotations": 0,
                                     "depr_decreases": 0, "depr_end": 0})
        entered = asset.in_service_date or asset.acquired_on
        out = asset.disposal_date if asset.status in ("sold", "scrapped") else None
        if entered > fy.end_date or (out and out < fy.start_date):
            continue
        before = accumulated(asset, before=fy.start_date)
        during = sum(d.amount_cents for d in asset.depreciations if d.fiscal_year_id == fy.id)
        if entered < fy.start_date:
            row["gross_start"] += asset.acquisition_cents
            row["depr_start"] += before
        else:
            row["increases"] += asset.acquisition_cents
        row["dotations"] += during
        if out and out <= fy.end_date:
            row["decreases"] += asset.acquisition_cents
            row["depr_decreases"] += before + during
    for row in rows.values():
        row["gross_end"] = row["gross_start"] + row["increases"] - row["decreases"]
        row["depr_end"] = row["depr_start"] + row["dotations"] - row["depr_decreases"]
    return [r for _, r in sorted(rows.items()) if any(isinstance(v, int) and v for v in r.values())]
