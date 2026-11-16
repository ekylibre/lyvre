"""Subventions d'investissement (lot AG3.d, claudedocs/design_aides_pac.md § 6, AGD20 Q-P3 et Q-P7).

- **Octroi** : à la décision, D 441 / C 131 (journal OD, source `AID_GRANT`), avant tout versement ; les virements
  rattachés ensuite soldent le 441 (AG3.b). Sans octroi, la pratique « versement directement en 131 » reste possible.
- **Immobilisations financées** (`aid_assets`) : montant affecté à chacune, au plus la part d'investissement.
- **Reprise** à chaque exercice : montant affecté × dotation de l'exercice ÷ base amortissable de l'immobilisation
  (plan d'amortissement d'`assets.schedule`), la dernière reprise soldant l'arrondi ; à la sortie de l'immobilisation,
  le reste. Écriture D 139 / C 747 au dernier jour (source `AID_RELEASE`, non extournée), regénérée tant que
  l'exercice est ouvert ; les reprises passées sont figées (`aid_releases`).
- **Bien non amortissable** (terre) : pas de reprise calculée ; une reprise saisie se justifie par un motif (Q-P7).
- Aide mixte (DJA) : sa part d'investissement suit ces règles, sa part d'exploitation l'AG3.c.
Au micro-BA (comptabilité simplifiée), rien : registre seulement.
"""
from __future__ import annotations

from datetime import date

from app.extensions import db
from app.models import Account, Aid, AidAsset, AidRelease, Asset, FiscalYear, JournalEntry
from app.models.journal_entry import SOURCE_AID_GRANT, SOURCE_AID_RELEASE
from app.services import aids
from app.services.aids import AidError

MIN_REASON = 5
ACCOUNTS = {"139": ("Subventions d'investissement inscrites au compte de résultat", "EQUITY"),
            "747": ("Quote-part des subventions d'investissement virée au résultat de l'exercice", "REVENUE"),
            "441": ("État - Subventions et aides à recevoir", "TIERS")}


def enabled() -> bool:
    from app.services import aid_closing
    return aid_closing.enabled()


def _require():
    if not enabled():
        raise AidError("Écritures réservées aux exploitations au réel (partie double).", status=409)


def _account(code: str) -> Account:
    account = Account.query.filter_by(code=code, is_header=False).first()
    if account is None:
        label, kind = ACCOUNTS[code]
        account = Account(code=code, label=label, account_type=kind)
        db.session.add(account)
        db.session.flush()
    return account


def _journal():
    from app.services.assets import _journal as od
    return od()


def investment_cents(aid: Aid) -> int:
    if aid.status == "refused":
        return 0
    if aid.nature == "investment":
        return aids.acquired_cents(aid)
    if aid.nature == "mixed":
        return aid.investment_share_cents or 0
    return 0


def investment_paid(aid: Aid, until: date | None = None) -> int:
    paid = aids.paid_cents(aid, until)
    if aid.nature == "investment":
        return paid
    total = aids.acquired_cents(aid)
    return round(paid * (aid.investment_share_cents or 0) / total) if aid.nature == "mixed" and total else 0


def _fy_for(day: date) -> FiscalYear:
    fy = FiscalYear.query.filter(FiscalYear.start_date <= day, FiscalYear.end_date >= day).first()
    if fy is None:
        raise AidError(f"Aucun exercice ne couvre le {day:%d/%m/%Y} : créez-le d'abord.", status=409)
    if fy.status != "open":
        raise AidError(f"Exercice {fy.label} clôturé : rouvrez-le pour modifier ses écritures.", status=409)
    return fy


# ------------------------------------------------------------------ octroi

def grant(aid: Aid) -> JournalEntry:
    """Écriture d'octroi D 441 / C 131 à la date de la décision (sans commit)."""
    from app.services.ledger import post_entry

    _require()
    if aid.nature not in ("investment", "mixed"):
        raise AidError("Octroi réservé aux subventions d'investissement.", status=409)
    if aid.grant_entry_id is not None:
        raise AidError("Octroi déjà passé.", status=409)
    if aid.decision_on is None:
        raise AidError("Saisissez la date de la décision d'attribution.", "decision_on")
    amount = investment_cents(aid)
    if amount <= 0:
        raise AidError("Montant d'investissement à saisir (notifié, ou part d'investissement de l'aide mixte).",
                       "notified_cents")
    if aid.payments:
        raise AidError("Des versements sont déjà enregistrés : l'octroi se passe avant le premier versement (les "
                       "versements comptabilisés en 131 tiennent lieu d'octroi).", status=409)
    fy = _fy_for(aid.decision_on)
    label = f"Octroi — {aid.label} {aid.campaign}"
    entry = post_entry(fy.id, _journal().id, aid.decision_on, label, [
        {"account_id": _account("441").id, "label": label[:300], "debit_cents": amount, "credit_cents": 0},
        {"account_id": aid.account_id, "label": label[:300], "debit_cents": 0, "credit_cents": amount}],
        source=SOURCE_AID_GRANT, source_ref=f"aid-grant:{aid.id}", commit=False)
    aid.grant_entry_id = entry.id
    db.session.flush()
    return entry


def cancel_grant(aid: Aid) -> None:
    from app.services.ledger import delete_entries

    entry = aid.grant_entry
    if entry is None:
        raise AidError("Aucun octroi passé.", status=404)
    if aid.payments:
        raise AidError("Des versements soldent déjà l'octroi : détachez-les d'abord.", status=409)
    if entry.fiscal_year.status != "open":
        raise AidError("Exercice de l'octroi clôturé : rouvrez-le d'abord.", status=409)
    if entry.is_validated:
        raise AidError("Écriture d'octroi validée : annulez d'abord son lot de validation.", status=409)
    aid.grant_entry_id = None
    db.session.flush()
    (outcome,) = delete_entries([entry.id], allow_managed=True)
    if outcome["status"] != "ok":
        raise AidError(outcome.get("message") or "Suppression impossible.", status=409)


# ------------------------------------------------------------------ immobilisations financées

def set_assets(aid: Aid, rows) -> None:
    if aid.nature not in ("investment", "mixed"):
        raise AidError("Seule une subvention d'investissement finance des immobilisations.", "assets")
    if not isinstance(rows, list):
        raise AidError("Liste d'immobilisations attendue.", "assets")
    if any(r.entry_id for r in aid.releases if r.kind != "manual"):
        raise AidError("Des reprises sont déjà passées : annulez celles de l'exercice ouvert avant de changer les "
                       "immobilisations financées.", "assets", 409)
    links, seen = [], set()
    for row in rows:
        asset_id = row.get("asset_id") if isinstance(row, dict) else None
        asset = db.session.get(Asset, asset_id) if isinstance(asset_id, int) and not isinstance(asset_id, bool) else None
        if asset is None:
            raise AidError("Immobilisation introuvable.", "assets", 404)
        if asset.id in seen:
            raise AidError(f"« {asset.label} » figure deux fois.", "assets")
        seen.add(asset.id)
        amount = row.get("amount_cents")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise AidError("Montant affecté positif attendu.", "assets")
        links.append((asset, amount))
    total, limit = sum(a for _, a in links), investment_cents(aid)
    if limit and total > limit:
        raise AidError(f"Le total affecté ({total / 100:.2f} €) dépasse la subvention ({limit / 100:.2f} €).".replace(".", ","),
                       "assets")
    aid.assets.clear()
    db.session.flush()
    for asset, amount in links:
        aid.assets.append(AidAsset(asset_id=asset.id, amount_cents=amount))
    db.session.flush()


# ------------------------------------------------------------------ reprises

def release_entry(fy: FiscalYear) -> JournalEntry | None:
    return JournalEntry.query.filter_by(fiscal_year_id=fy.id, source=SOURCE_AID_RELEASE).first()


def _prior(aid_id: int, asset_id: int | None, fy: FiscalYear) -> int:
    rows = (AidRelease.query.join(FiscalYear, FiscalYear.id == AidRelease.fiscal_year_id)
            .filter(AidRelease.aid_id == aid_id, AidRelease.asset_id == asset_id, AidRelease.entry_id.isnot(None),
                    FiscalYear.start_date < fy.start_date))
    return sum(r.amount_cents for r in rows)


def _row(aid, asset, kind, amount, fy, *, dotation=None, base=None, posted=False, release=None):
    return {"aid_id": aid.id, "aid_label": f"{aid.label} {aid.campaign}", "asset_id": asset.id if asset else None,
            "asset_label": asset.label if asset else None, "kind": kind, "amount_cents": amount,
            "dotation_cents": dotation, "base_cents": base, "posted": posted,
            "release_id": release.id if release else None, "reason": release.reason if release else None}


def _computed(fy: FiscalYear) -> list[dict]:
    from app.services.assets import schedule

    out = []
    for aid in Aid.query.filter(Aid.nature.in_(("investment", "mixed")), Aid.status != "refused").order_by(Aid.id):
        for link in aid.assets:
            asset = link.asset
            remaining = link.amount_cents - _prior(aid.id, asset.id, fy)
            if remaining <= 0:
                continue
            if asset.status in ("sold", "scrapped") and asset.disposal_date and asset.disposal_date <= fy.end_date:
                if asset.disposal_date >= fy.start_date:
                    out.append(_row(aid, asset, "disposal", remaining, fy))
                continue
            if asset.method == "none":
                continue                                   # bien non amortissable : reprise saisie seulement
            row = next((r for r in schedule(asset) if r.fiscal_year_id == fy.id), None)
            base = asset.base_cents
            if row is None or row.amount_cents <= 0 or base <= 0:
                continue
            last = row.cumulative_cents >= base
            amount = remaining if last else min(remaining, round(link.amount_cents * row.amount_cents / base))
            if amount > 0:
                out.append(_row(aid, asset, "depreciation", amount, fy, dotation=row.amount_cents, base=base))
    return out


def releases(fy: FiscalYear) -> list[dict]:
    """Reprises de l'exercice : figées si l'écriture est passée, calculées sinon ; reprises saisies comprises."""
    entry = release_entry(fy)
    stored = AidRelease.query.filter_by(fiscal_year_id=fy.id).order_by(AidRelease.id).all()
    manual = [_row(r.aid, r.asset, "manual", r.amount_cents, fy, posted=r.entry_id is not None, release=r)
              for r in stored if r.kind == "manual"]
    if entry is not None:
        auto = [_row(r.aid, r.asset, r.kind, r.amount_cents, fy, posted=True, release=r)
                for r in stored if r.kind != "manual"]
        return auto + manual
    return _computed(fy) + manual


def cancel_releases(fy: FiscalYear) -> None:
    from app.services.ledger import delete_entries

    entry = release_entry(fy)
    if entry is None:
        return
    if fy.status != "open":
        raise AidError("Exercice clôturé : les reprises sont figées.", status=409)
    if entry.is_validated:
        raise AidError("Écriture de reprise validée : annulez d'abord son lot de validation.", status=409)
    AidRelease.query.filter(AidRelease.fiscal_year_id == fy.id, AidRelease.kind != "manual").delete()
    for row in AidRelease.query.filter_by(fiscal_year_id=fy.id, kind="manual"):
        row.entry_id = None
    db.session.flush()
    (outcome,) = delete_entries([entry.id], allow_managed=True)
    if outcome["status"] != "ok":
        raise AidError(outcome.get("message") or "Suppression impossible.", status=409)


def post_releases(fy: FiscalYear) -> JournalEntry | None:
    """Passe (ou repasse) les reprises de l'exercice : une écriture OD au dernier jour (sans commit)."""
    from app.services.ledger import post_entry

    _require()
    if fy.status != "open":
        raise AidError("Exercice clôturé : rouvrez-le pour passer les reprises.", status=409)
    cancel_releases(fy)
    db.session.expire_all()
    rows = releases(fy)
    if not rows:
        return None
    debit, credit = _account("139"), _account("747")
    lines = []
    for r in rows:
        text = f"{r['aid_label']}{' — ' + r['asset_label'] if r['asset_label'] else ''}"[:300]
        lines += [{"account_id": debit.id, "label": text, "debit_cents": r["amount_cents"], "credit_cents": 0},
                  {"account_id": credit.id, "label": text, "debit_cents": 0, "credit_cents": r["amount_cents"]}]
    entry = post_entry(fy.id, _journal().id, fy.end_date, f"Reprise des subventions d'investissement {fy.label}", lines,
                       source=SOURCE_AID_RELEASE, commit=False)
    for r in rows:
        if r["kind"] == "manual":
            db.session.get(AidRelease, r["release_id"]).entry_id = entry.id
        else:
            db.session.add(AidRelease(aid_id=r["aid_id"], fiscal_year_id=fy.id, asset_id=r["asset_id"], kind=r["kind"],
                                      amount_cents=r["amount_cents"], entry_id=entry.id))
    db.session.flush()
    return entry


def add_manual(fy: FiscalYear, aid_id, amount, reason, asset_id=None) -> AidRelease:
    _require()
    if fy.status != "open":
        raise AidError("Exercice clôturé.", status=409)
    aid = db.session.get(Aid, aid_id) if isinstance(aid_id, int) and not isinstance(aid_id, bool) else None
    if aid is None or aid.nature not in ("investment", "mixed"):
        raise AidError("Subvention d'investissement introuvable.", "aid_id", 404)
    if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
        raise AidError("Montant positif attendu.", "amount_cents")
    text = str(reason or "").strip()[:500]
    if len(text) < MIN_REASON:
        raise AidError("Motif obligatoire pour une reprise saisie (5 caractères au moins).", "reason")
    if asset_id is not None and not any(link.asset_id == asset_id for link in aid.assets):
        raise AidError("Immobilisation non financée par cette subvention.", "asset_id")
    released = sum(r.amount_cents for r in aid.releases if r.entry_id is not None or r.fiscal_year_id == fy.id)
    if released + amount > investment_cents(aid):
        raise AidError("La reprise dépasse le reste de la subvention.", "amount_cents")
    row = AidRelease(aid_id=aid.id, fiscal_year_id=fy.id, asset_id=asset_id, kind="manual", amount_cents=amount,
                     reason=text)
    db.session.add(row)
    db.session.flush()
    return row


def delete_manual(fy: FiscalYear, release_id) -> None:
    row = db.session.get(AidRelease, release_id) if isinstance(release_id, int) else None
    if row is None or row.fiscal_year_id != fy.id or row.kind != "manual":
        raise AidError("Reprise saisie introuvable.", status=404)
    if row.entry_id is not None:
        raise AidError("Reprise déjà passée : annulez d'abord l'écriture de reprise de l'exercice.", status=409)
    db.session.delete(row)
    db.session.flush()


# ------------------------------------------------------------------ annexe

def annex(fy: FiscalYear) -> list[dict]:
    """Tableau des subventions d'investissement : montant, reprises antérieures et de l'exercice, reste (131 − 139)."""
    this_year: dict[int, int] = {}
    for r in releases(fy):
        this_year[r["aid_id"]] = this_year.get(r["aid_id"], 0) + r["amount_cents"]
    out = []
    for aid in Aid.query.filter(Aid.nature.in_(("investment", "mixed")), Aid.status != "refused").order_by(Aid.campaign, Aid.id):
        amount = investment_cents(aid)
        before = sum(r.amount_cents for r in aid.releases if r.entry_id is not None and r.fiscal_year
                     and r.fiscal_year.start_date < fy.start_date)
        current = this_year.get(aid.id, 0)
        if not amount and not before and not current:
            continue
        assigned = sum(link.amount_cents for link in aid.assets)
        out.append({"aid_id": aid.id, "label": f"{aid.label} {aid.campaign}", "account_code": aid.account.code,
                    "amount_cents": amount, "released_before_cents": before, "released_cents": current,
                    "remaining_cents": amount - before - current, "assigned_cents": assigned,
                    "granted": aid.grant_entry_id is not None,
                    "assets": [{"asset_id": link.asset_id, "label": link.asset.label, "amount_cents": link.amount_cents,
                                "method": link.asset.method} for link in aid.assets]})
    return out


def warnings(aid: Aid) -> list[str]:
    if aid.nature not in ("investment", "mixed") or aid.status == "refused":
        return []
    amount, assigned = investment_cents(aid), sum(link.amount_cents for link in aid.assets)
    out = []
    if amount and assigned < amount:
        out.append(f"Immobilisations financées : {assigned / 100:.2f} € affectés sur {amount / 100:.2f} € ; la part non "
                   "affectée ne sera pas reprise.".replace(".", ",", 2))
    return out


def receivable_cents(fy: FiscalYear) -> int:
    """Octrois restant à percevoir à la clôture (441), pour le contrôle du solde du 441 (AG3.c)."""
    total = 0
    for aid in Aid.query.filter(Aid.grant_entry_id.isnot(None)):
        entry = aid.grant_entry
        if entry is not None and entry.entry_date <= fy.end_date:
            total += investment_cents(aid) - investment_paid(aid, fy.end_date)
    return total
