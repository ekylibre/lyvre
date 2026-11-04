"""Détections de l'échéancier (lot AG9a.c, claudedocs/design_echeancier_agricole.md § 6.2) : ce que l'exploitation
doit vérifier ou décider, lu dans les données de Lyvre et le profil des démarches.

Chaque détection : `{id, level, title, detail, link, link_label}` ; `level` vaut `warning` (à traiter) ou `info`.
Une détection qui échoue est journalisée et omise : elle ne bloque pas l'échéancier.

Viennent après les lots dont elles dépendent : virement ASP non rattaché (AG3), BA estimé contre base du PAS (AG5),
DEP (AG6).
"""
from __future__ import annotations

from datetime import date, timedelta

from flask import current_app

from app.extensions import db
from app.models import BankTransaction, FiscalYear, RfaClaim, TaxOption, VatReturn
from app.services import deadlines, reg_params

RENOUNCE_NOTICE_DAYS = 60
UNRECONCILED_DAYS = 30
PARAM_NOTICE_DAYS = 90
PROFILE_NOTICE_DAYS = 183
LEASE_NOTICE_DAYS = 15
VAT_DECLARING = ("rsa_installments", "rsa_quarterly", "rsa_monthly", "normal")
TAX_LINK = "/configuration/organization?tab=tax"
ACTIVITIES_LINK = "/configuration/organization?tab=activities"


def _fr(day: date) -> str:
    return day.strftime("%d/%m/%Y")


def _euros(cents: int) -> str:
    return f"{cents / 100:,.2f}".replace(",", " ").replace(".", ",") + " €"


def _item(id_, level, title, detail, link=None, link_label=None) -> dict:
    return {"id": id_, "level": level, "title": title, "detail": detail, "link": link, "link_label": link_label}


# ------------------------------------------------------------------ TVA

def _vat_setup(today: date, ctx: deadlines.Context) -> list[dict]:
    regime = ctx.tax_value("vat_regime", today)
    if regime not in VAT_DECLARING:
        return []
    fy = FiscalYear.query.filter(FiscalYear.start_date <= today, FiscalYear.end_date >= today).first()
    if fy is None or fy.vat_period:
        return []
    return [_item("vat_setup", "warning", "TVA de l'exercice non paramétrée",
                  f"Le profil fiscal indique un régime de TVA déclaratif, mais l'exercice {fy.label} ne prépare pas sa TVA "
                  "dans Lyvre : ses déclarations et acomptes n'apparaissent pas dans l'échéancier.",
                  "/fiscal-years/", "Paramétrer l'exercice")]


def _vat_credit(today: date, ctx: deadlines.Context) -> list[dict]:
    from app.services import vat_return

    out = []
    for form, key, word in (("CA3", "vat.rsa.refund_min_period_cents", "la période"),
                            ("CA12A", "vat.rsa.refund_min_annual_cents", "l'année")):
        last = VatReturn.query.filter_by(form=form).order_by(VatReturn.period_end.desc()).first()
        if last is None or last.refund_cents or not last.credit_cents:
            continue
        minimum = reg_params.value(key, last.period_end, default=None)
        if minimum is None or last.credit_cents < minimum:
            continue
        out.append(_item(f"vat_credit_{form.lower()}", "info", "Crédit de TVA remboursable",
                         f"La {form} {vat_return.period_label(last.period_start, last.period_end)} laisse un crédit de "
                         f"{_euros(last.credit_cents)}, au-dessus du minimum de {_euros(minimum)} pour {word} : "
                         "le remboursement se demande avec la déclaration suivante (formulaire 3519).",
                         f"/vat-returns/{vat_return.period_key(last.period_start, last.period_end)}", "Ouvrir la déclaration"))
    return out


def _rfa(today: date, ctx: deadlines.Context) -> list[dict]:
    from app.services import rfa

    year = today.year - 1
    if ctx.tax_value("vat_regime", date(year, 12, 31)) != "rfa":
        return []
    data = rfa.compute(year, today)
    out = []
    threshold = data["threshold"]
    if threshold["over"]:
        limit = threshold["threshold_cents"] * threshold["factor"]
        out.append(_item("rfa_threshold", "warning", "Passage obligatoire au régime simplifié agricole",
                         f"Moyenne des recettes de {year - 1} et {year} : {_euros(threshold['average_cents'])}, au-delà de "
                         f"{_euros(limit)}. Le remboursement forfaitaire cesse au 1er janvier {year + 1} "
                         "(CGI art. 298 bis) : déclarez la TVA au RSA.", TAX_LINK, "Mettre à jour le profil fiscal"))
    if RfaClaim.query.filter_by(year=year).first() is None:
        missing = [c for c in data["clients"] if any(i.startswith("Attestation") for i in c["issues"])]
        if missing:
            out.append(_item("rfa_attestations", "warning", f"Attestations d'achats {year} manquantes",
                             f"{len(missing)} client{'s' if len(missing) > 1 else ''} sans attestation conforme pour la "
                             f"demande de remboursement forfaitaire (3520) de {year}.", f"/rfa/?year={year}",
                             "Ouvrir la demande"))
    return out


# ------------------------------------------------------------------ régimes et options

def _micro(today: date, ctx: deadlines.Context) -> list[dict]:
    from app.services import micro_ba

    if ctx.tax_value("ba_regime", today) != "micro":
        return []
    year = today.year - 1
    data = micro_ba.summary(year)
    if data["average_cents"] is None or data["threshold_cents"] is None or data["average_cents"] <= data["threshold_cents"]:
        return []
    return [_item("micro_threshold", "warning", "Sortie du micro-BA",
                  f"Moyenne des recettes de {year - 2} à {year} : {_euros(data['average_cents'])}, au-delà du seuil de "
                  f"{_euros(data['threshold_cents'])}. Le bénéfice relève du régime réel à compter de {year + 1} "
                  "(CGI art. 69).", TAX_LINK, "Mettre à jour le profil fiscal")]


def _renounce(today: date, ctx: deadlines.Context) -> list[dict]:
    from app.services import tax_profile

    out = []
    for option in TaxOption.query.order_by(TaxOption.start_date):
        info = tax_profile.renounce_by(option, today)
        if not info or not info.get("date"):
            continue
        limit = date.fromisoformat(info["date"])
        if today <= limit <= today + timedelta(days=RENOUNCE_NOTICE_DAYS):
            label = tax_profile.OPTIONS.get(option.code, option.code)
            out.append(_item(f"renounce_{option.id}", "warning", f"{label} : renonciation avant le {_fr(limit)}",
                             "Sans renonciation à cette date, l'option se poursuit pour une nouvelle période."
                             + (" Date à confirmer." if info.get("reliability") == "I" else ""), TAX_LINK,
                             "Voir les options"))
    return out


# ------------------------------------------------------------------ banque et paramètres

def _unreconciled(today: date, ctx: deadlines.Context) -> list[dict]:
    limit = today - timedelta(days=UNRECONCILED_DAYS)
    count = (db.session.query(db.func.count(BankTransaction.id))
             .filter(BankTransaction.reconciled.is_(False), BankTransaction.is_reversed.is_(False),
                     BankTransaction.transaction_date < limit).scalar())
    if not count:
        return []
    return [_item("unreconciled", "warning", "Relevés non rapprochés",
                  f"{count} transaction{'s' if count > 1 else ''} de plus de {UNRECONCILED_DAYS} jours "
                  f"{'ne sont pas rapprochées' if count > 1 else 'n’est pas rapprochée'} : les paiements des échéances "
                  "et la TVA en dépendent.", "/reconciliation/", "Rapprocher")]


def _params(today: date, ctx: deadlines.Context, items: list[dict]) -> list[dict]:
    end = today + timedelta(days=PARAM_NOTICE_DAYS)
    labels = []
    for item in items:
        if item["to_confirm"] and today <= item["date"] <= end and not item["managed"]:
            label = f"{item['label']} ({_fr(item['date'])})"
            if label not in labels:
                labels.append(label)
    if not labels:
        return []
    return [_item("params", "info", "Dates à confirmer",
                  "Date de l'année pas encore publiée ou à valider, reprise de la date habituelle pour : "
                  + ", ".join(labels) + ".", "/regulatory-values/", "Paramètres réglementaires")]


# ------------------------------------------------------------------ profil des démarches

def _profile(today: date, ctx: deadlines.Context) -> list[dict]:
    profile, out = ctx.profile, []
    soon = today + timedelta(days=PROFILE_NOTICE_DAYS)
    if profile.get("certiphyto_expires_on"):
        end = date.fromisoformat(profile["certiphyto_expires_on"])
        if end <= soon:
            out.append(_item("certiphyto", "warning", "Certiphyto à renouveler",
                             f"Le Certiphyto {'a expiré le' if end < today else 'expire le'} {_fr(end)} : le renouvellement "
                             "(formation ou test) est nécessaire pour acheter et utiliser des produits phytosanitaires.",
                             ACTIVITIES_LINK, "Activités et démarches"))
    if profile.get("young_farmer") and profile.get("young_farmer_since"):
        since = date.fromisoformat(profile["young_farmer_since"])
        end = deadlines._day_in(*deadlines._add_months(since, 48), since.day)
        if today <= end <= soon:
            out.append(_item("young_farmer", "info", "Fin du plan d'entreprise JA",
                             f"Le plan d'entreprise de l'installation aidée se termine vers le {_fr(end)} : "
                             "rassemblez les justificatifs du respect des engagements.", ACTIVITIES_LINK,
                             "Activités et démarches"))
    for lease in profile.get("leases") or []:
        month, day = (int(p) for p in lease["due"].split("-"))
        due = date(today.year, month, day)
        if due < today:
            due = date(today.year + 1, month, day)
        if due <= today + timedelta(days=LEASE_NOTICE_DAYS):
            who = ("envoyez l'avis d'échéance au preneur" if lease["role"] == "landlord"
                   else "vérifiez le montant appelé par le bailleur")
            out.append(_item(f"lease_{lease['due']}_{lease['label'][:20]}", "info",
                             f"Fermage « {lease['label']} » le {_fr(due)}",
                             f"Montant indexé sur l'indice national des fermages en vigueur (applicable du 1er octobre au "
                             f"30 septembre) : {who}.", ACTIVITIES_LINK, "Activités et démarches"))
    return out


CHECKS = (_vat_setup, _vat_credit, _rfa, _micro, _renounce, _unreconciled, _profile)


def detections(today: date | None = None, ctx: deadlines.Context | None = None, items: list[dict] | None = None) -> list[dict]:
    """Détections du jour, les avertissements d'abord. `items` : occurrences déjà calculées (dates à confirmer)."""
    today = today or date.today()
    ctx = ctx or deadlines.context()
    out = []
    for check in CHECKS:
        try:
            out.extend(check(today, ctx))
        except Exception:  # une détection ne bloque pas l'échéancier
            current_app.logger.exception("Détection %s en échec", check.__name__)
    if items is not None:
        out.extend(_params(today, ctx, items))
    out.sort(key=lambda d: d["level"] != "warning")
    return out

