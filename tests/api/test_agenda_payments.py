"""Lot AG9a.c : paiements reconnus sur les relevés et détections de l'échéancier.

Recette : un prélèvement DGFiP du 05/11/2026 coche l'acompte de TVA du 5/11 (1 001 € proposés, US-A2).
"""
from datetime import date

import pytest

from app.extensions import db
from app.models import BankAccount, BankTransaction, DeadlineState, TaxOption, TaxProfile, VatReturn
from app.services import agenda, agenda_checks, agri_profile, deadlines
from test_agenda import MONDAY, _find, farm  # noqa: F401

THURSDAY = date(2026, 11, 6)


def _bank(farm):
    bank = BankAccount(label="CIC", account_id=farm["512"].id)
    db.session.add(bank)
    db.session.commit()
    return bank


def _debit(bank, day, cents, label, n=[0]):
    n[0] += 1
    tx = BankTransaction(bank_account_id=bank.id, fitid=f"T{n[0]}", transaction_date=day, amount_cents=-cents, label=label)
    db.session.add(tx)
    db.session.commit()
    return tx


def _installment(day=THURSDAY):
    (item,) = _find(agenda.occurrences(date(2026, 11, 1), date(2026, 11, 30), day)["items"], "TVA-02")
    return item


def test_normalize_and_payees():
    assert deadlines.normalize("Prlv SEPA D.G.F.I.P. Impôts") == "PRLV SEPA DGFIP IMPOTS"
    tx = BankTransaction(label="PRLV SIEMENS FINANCE", amount_cents=-100)
    assert not agenda.payee_matches(tx, "SIE")
    assert agenda.payee_matches(BankTransaction(label="PRLV SEPA DGFIP TVA", amount_cents=-1), "SIE")
    assert agenda.payee_matches(BankTransaction(label="PRELEVEMENT", counterparty="M.S.A. Nord", amount_cents=-1), "MSA")
    assert agenda.payee_matches(BankTransaction(label="REDEVANCE AGENCE DE L'EAU", amount_cents=-1), "Agence de l'eau")


def test_dgfip_debit_ticks_the_installment(farm):
    bank = _bank(farm)
    _debit(bank, date(2026, 11, 5), 50000, "PRLV SEPA DGFIP")            # montant trop éloigné
    good = _debit(bank, date(2026, 11, 5), 100100, "PRLV SEPA DGFIP IMPOT 3525BIS")
    _debit(bank, date(2026, 11, 4), 100100, "PRLV EDF")                  # autre payeur
    created = agenda.match_payments(THURSDAY)
    db.session.commit()
    assert [(s.deadline_id, s.occurs_on, s.bank_transaction_id) for s in created] == [("TVA-02#1", date(2026, 11, 5), good.id)]
    item = _installment()
    assert item["status"] == "done" and item["state"]["origin"] == "bank"
    assert item["state"]["transaction"]["amount_cents"] == -100100 and item["state"]["done_on"] == "2026-11-05"
    assert agenda.match_payments(THURSDAY) == []                         # idempotent


def test_unlink_then_link_by_hand(farm):
    client = farm["client"]
    bank = _bank(farm)
    first = _debit(bank, date(2026, 11, 5), 100100, "PRLV DGFIP")
    other = _debit(bank, date(2026, 11, 9), 99000, "VIR TRESOR PUBLIC")
    agenda.match_payments(THURSDAY)
    db.session.commit()
    state = DeadlineState.query.one()
    assert client.delete(f"/api/v1/agenda/states/{state.id}").status_code == 200
    assert DeadlineState.query.one().status == "unlinked"
    assert agenda.match_payments(THURSDAY) == []                         # plus de rapprochement automatique
    item = _installment()
    assert item["status"] == "late" and item["unlinked"] and item["state"] is None
    query = {"deadline_id": item["deadline_id"], "occurs_on": "2026-11-05", "period": item["period"]}
    found = client.get("/api/v1/agenda/candidates", query_string=query).get_json()["items"]
    assert [c["id"] for c in found] == [first.id, other.id] and found[0]["amount_matches"] is True
    payload = {"deadline_id": item["deadline_id"], "occurs_on": "2026-11-05", "period": item["period"], "status": "done"}
    resp = client.post("/api/v1/agenda/states", json={**payload, "bank_transaction_id": other.id})
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()["item"]["transaction"]["id"] == other.id and DeadlineState.query.count() == 1
    assert client.post("/api/v1/agenda/states", json={**payload, "bank_transaction_id": other.id}).status_code == 409


def test_non_payment_events_are_not_linked(farm):
    bank = _bank(farm)
    tx = _debit(bank, date(2027, 5, 4), 50000, "PRLV DGFIP")
    agenda.match_payments(date(2027, 5, 6))
    assert all(s.deadline_id != "FIS-01#1" for s in DeadlineState.query)    # liasse : pas un paiement
    with pytest.raises(agenda.AgendaError):
        agenda.set_state("FIS-01#1", date(2027, 5, 4), "2026", "done", today=date(2027, 5, 6), bank_transaction_id=tx.id)


def test_get_agenda_matches_and_detects(farm):
    bank = _bank(farm)
    _debit(bank, date(2026, 11, 5), 100100, "PRLV DGFIP")
    _debit(bank, date(2026, 9, 1), 1200, "FRAIS")                        # non rapprochée depuis plus de 30 jours
    body = farm["client"].get("/api/v1/agenda").get_json()
    assert DeadlineState.query.filter_by(origin="bank").count() == 1
    ids = [d["id"] for d in body["detections"]]
    assert "unreconciled" in ids


def test_detections(farm, caplog):
    farm["fy"].vat_period = None
    db.session.add(TaxOption(code="vat_quarterly", start_date=date(2022, 1, 1), duration_years=5, tacit_renewal=True))
    VatReturn.query.filter_by(form="CA12A").one().credit_cents = 40000   # CA12A 2025 du jeu US-A2
    agri_profile.save({"certiphyto_expires_on": "2027-03-01", "leases": [{"label": "Bail Nord", "due": "12-25",
                                                                          "role": "landlord"}]})
    db.session.commit()
    ctx = deadlines.context()
    found = {d["id"]: d for d in agenda_checks.detections(date(2026, 12, 15), ctx, [])}
    assert "vat_setup" in found and found["vat_setup"]["level"] == "warning"
    assert "05/02/2027" in found[next(k for k in found if k.startswith("renounce_"))]["title"]
    assert "400,00 €" in found["vat_credit_ca12a"]["detail"]
    assert "certiphyto" in found and "envoyez l'avis" in found[next(k for k in found if k.startswith("lease_"))]["detail"]
    assert "en échec" not in caplog.text
    assert [d["level"] for d in found.values()] == sorted((d["level"] for d in found.values()), key=lambda lv: lv != "warning")


def test_rfa_and_micro_detections(farm, caplog):
    TaxProfile.query.filter_by(kind="vat_regime").one().value = "rfa"
    TaxProfile.query.filter_by(kind="ba_regime").one().value = "micro"
    db.session.commit()
    found = agenda_checks.detections(date(2026, 11, 2), deadlines.context(), [])
    assert all(not d["id"].startswith("vat_") for d in found)           # plus au RSA
    assert "rfa_threshold" not in [d["id"] for d in found]               # recettes 2025 sous le seuil
    assert "en échec" not in caplog.text


def test_params_to_confirm():
    item = {"to_confirm": True, "date": date(2027, 1, 10), "managed": False, "label": "Appel de cotisations MSA"}
    (found,) = agenda_checks._params(date(2026, 12, 1), None, [item, dict(item)])
    assert found["detail"].count("Appel de cotisations MSA") == 1
    assert agenda_checks._params(date(2026, 6, 1), None, [item]) == []    # au-delà de 90 jours


def test_threshold_detections(farm, monkeypatch):
    from app.services import micro_ba, rfa

    TaxProfile.query.filter_by(kind="vat_regime").one().value = "rfa"
    TaxProfile.query.filter_by(kind="ba_regime").one().value = "micro"
    db.session.commit()
    monkeypatch.setattr(rfa, "compute", lambda year, today=None: {
        "threshold": {"over": True, "threshold_cents": 4600000, "factor": 2, "average_cents": 9500000},
        "clients": [{"issues": ["Attestation d'achats manquante."]}]})
    monkeypatch.setattr(micro_ba, "summary", lambda year: {"average_cents": 13000000, "threshold_cents": 12000000})
    found = {d["id"]: d for d in agenda_checks.detections(date(2026, 11, 2), deadlines.context(), [])}
    assert "92 000,00 €" in found["rfa_threshold"]["detail"] and "1er janvier 2026" in found["rfa_threshold"]["detail"]
    assert found["rfa_attestations"]["link"] == "/rfa/?year=2025"
    assert "à compter de 2026" in found["micro_threshold"]["detail"]
