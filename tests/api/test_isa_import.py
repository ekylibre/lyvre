"""Lot AG10.b : import d'un export Isacompta (.ISA). Extrait **fictif** construit avec la disposition relevée
(app/services/isa_import.py) ; aucune donnée réelle."""
import io
import json
from datetime import date

import pytest

from app.models import (
    Account, Activity, ActivityProduction, AnalyticAllocation, AnalyticKey, AnalyticRule, JournalEntry, JournalLine,
    Lettering, Workshop,
)
from app.services import isa_import

from test_agri_fixtures import _agri_instance


def rec(kind, width, *fields):
    """Enregistrement à largeur fixe : `fields` = (début, fin, valeur, alignement « < » ou « > »)."""
    row = list(kind.ljust(width))
    for start, end, value, align in fields:
        text = (value.rjust if align == ">" else value.ljust)(end - start)[: end - start]
        row[start:end] = text
    return "".join(row).rstrip()


def ana(code, label, unit="", quantity=""):
    return rec("ANA", 80, (3, 12, code, ">"), (12, 54, label, ">"), (54, 66, unit, ">"), (66, 78, quantity, ">"))


def ana_link(kind, code, share="1000"):
    return rec(kind, 70, (6, 12, code, ">"), (12, 50, "SECTION", ">"), (55, 70, share, ">"))


def cpt(code, label):
    return rec("CPT", 292, (6, 16, code, "<"), (16, 46, label, ">"))


def ecr(journal, day, piece, label):
    return rec("ECR", 296, (6, 8, journal, "<"), (8, 16, day, "<"), (16, 24, piece, ">"), (24, 54, label, ">"))


def mvt(account, label, debit="", credit="", letter="", day=""):
    fields = [(6, 16, account, "<"), (16, 46, label, ">"), (46, 59, debit, ">"), (59, 72, credit, ">"),
              (106, 107, "1" if letter else "0", "<"), (143, 151, day, "<")]
    if letter:
        fields.append((107, 110, letter, "<"))
    return rec("MVT", 285, *fields)


def isa_file(unbalanced=False):
    rows = [
        "VER   020000000000                  ISA COMPTA0",
        rec("DOS", 72, (6, 13, "1234567", "<")),
        rec("EXO", 47, (6, 14, "01012025", "<"), (14, 22, "31122025", "<"), (35, 38, "EUR", "<")),
        ana("1", "GRANDES CULTURES", "ha", "30.000"), ana("11", "CEREALES"),
        ana("11111", "BLE TENDRE HIVER", "ha", "20.000"), ana("11171", "MAIS GRAIN", "ha", "10.000"),
        ana("CS", "CHARGES DE STRUCTURE"), ana("CS01", "MATERIEL"), ana("CS02", "BATIMENTS"),
        cpt("6011000000", "ENGRAIS & AMENDEMENT"), ana_link("ANACPT", "1"),
        cpt("6155000000", "ENTRETIEN MATERIEL"), ana_link("ANACPT", "CS01"),
        cpt("7011711100", "MAIS GRAINS"),
        rec("TVA", 112, (6, 8, "A5", "<"), (8, 38, "TVA ACHATS 20", ">"), (38, 48, "4456600000", "<"), (48, 55, "20", "<")),
        rec("JOU", 85, (6, 8, "AC", "<"), (8, 44, "ACHATS", ">")),
        rec("JOU", 85, (6, 8, "VT", "<"), (8, 44, "VENTES", ">")),
        rec("JOU", 85, (6, 8, "BQ", "<"), (8, 44, "BANQUE", ">")),
        ecr("", "01012025", "", ""),                                     # en-tête sans journal : ignoré
        ecr("AC", "15032025", "F1", "ENGRAIS COOP"),
        mvt("6011000000", "ENGRAIS", debit="1000.00", day="15032025"), ana_link("ANAMVT", "1"),
        mvt("4456600000", "TVA", debit="200.00", day="15032025"),
        mvt("401COOPAG", "COOP AGRICOLE", credit="1200.00", letter="AAA", day="15032025"),
        "ECHMVT    1200.0000       10015042025  00",
        ecr("AC", "02042025", "F2", "REPARATION"),
        mvt("6155000000", "REPARATION", debit="300.00", day="02042025"),
        mvt("401GARAGE", "GARAGE", credit="300.00" if not unbalanced else "310.00", day="02042025"),
        ecr("VT", "10102025", "V1", "VENTE MAIS"),
        mvt("411NEGOCE", "NEGOCE", debit="3000.00", day="10102025"),
        mvt("7011711100", "MAIS", credit="3000.00", day="10102025"), ana_link("ANAMVT", "11171"),
        ecr("BQ", "20032025", "R1", "REGLEMENT COOP"),
        mvt("401COOPAG", "COOP AGRICOLE", debit="1200.00", letter="AAA", day="20032025"),
        mvt("5120000000", "BANQUE", credit="1200.00", day="20032025"),
        "AFFLET1  TRANX  TRANX  2          301052025         204081000000",
        "POINTI       R004398 17   3746191607052025          74452000000",
    ]
    return ("\r\n".join(rows) + "\r\n").encode("cp850")


def _post(client, url, content, **form):
    return client.post(url, data={"file": (io.BytesIO(content), "DOSSIER.ISA"), **form}, content_type="multipart/form-data")


@pytest.fixture()
def farm(app, login_as):
    client = login_as(role="admin")
    _agri_instance()
    return client


def test_parse():
    isa = isa_import.parse(isa_file())
    assert (isa.start, isa.end) == (date(2025, 1, 1), date(2025, 12, 31))
    assert len(isa.entries) == 4 and isa.problems == []
    sale = next(e for e in isa.entries if e.journal == "VT")
    assert [(l.account, l.aux, l.debit, l.credit) for l in sale.lines] == [("411", "411NEGOCE", 300000, 0),
                                                                            ("70117111", "", 0, 300000)]
    assert isa.line_sections[id(sale.lines[1])] == [("11171", 1000)]
    assert isa.account_sections["6155000000"] == [("CS01", 1000)]
    assert isa.due_dates == 1 and isa.reconciliations == 1 and isa.vat_codes[0]["rate"] == "20"
    leaves = {s.code for s in isa_import._activity_sections(isa)}
    assert leaves == {"11111", "11171", "CS01", "CS02"}
    assert set(isa_import.default_sections(isa)) == {"11111", "11171", "CS01"}   # CS02 : ni ventilée, ni surface
    assert isa_import.account_code("6262000000") == ("62620000", "")
    assert isa_import.account_code("401DUPONT") == ("401", "401DUPONT")


def test_parse_refusals():
    with pytest.raises(isa_import.ImportError_):
        isa_import.parse(b"JournalCode\tEcritureNum\n")
    isa = isa_import.parse(isa_file(unbalanced=True))
    assert len(isa.problems) == 1 and "déséquilibrée" in isa.problems[0]


def test_analyze_and_import(farm):
    analysis = _post(farm, "/api/v1/imports/isa/analyze", isa_file()).get_json()
    assert analysis["entries"] == 4 and analysis["pcga1986"] is True
    assert analysis["fiscal_year"] == {"start_date": "2025-01-01", "end_date": "2025-12-31"}
    sections = {s["code"]: s for s in analysis["isa"]["sections"]}
    assert sections["11111"]["lexicon_name"] == "Blé tendre d’hiver" and sections["11111"]["workshop"] == "GRANDES CULTURES"
    assert not sections["CS02"]["proposed"]
    plan = {r["key"]: r for r in analysis["accounts"]}
    assert plan["60110000"]["target_code"] == "60111" and plan["70117111"]["target_code"] == "70117111"

    resp = _post(farm, "/api/v1/imports/isa", isa_file(), mode="history", start_date="2025-01-01", end_date="2025-12-31")
    body = resp.get_json()
    assert resp.status_code == 200, body
    assert body["entries"] == 4
    assert body["analytic"] == {"workshops": 2, "activities": 3, "measures": 2, "lines": 2, "rules": 2, "skipped": 0}
    assert JournalEntry.query.count() == 4 and Lettering.query.count() == 1
    wheat = Activity.query.filter_by(isacompta_code="11111").one()
    assert wheat.name == "Blé tendre d’hiver" and wheat.lexicon_reference and wheat.workshop.isacompta_code == "1"
    assert wheat.workshop.family == "plant_farming"
    assert ActivityProduction.query.filter_by(activity_id=wheat.id).one().measure == 20
    structure = Activity.query.filter_by(isacompta_code="CS01").one()
    assert structure.workshop.family == "administering"
    assert Activity.query.filter_by(isacompta_code="CS02").first() is None
    # Ligne ventilée sur la section « 1 » (regroupement) : clé « surface » sur blé et maïs.
    key = AnalyticKey.query.one()
    assert key.basis == "surface" and {m.activity.isacompta_code for m in key.members} == {"11111", "11171"}
    fert = JournalLine.query.join(Account).filter(Account.code == "60111").one()
    (alloc,) = fert.analytic_allocations
    assert alloc.key_id == key.id and alloc.share_bp == 10000 and alloc.origin == "import"
    maize = JournalLine.query.join(Account).filter(Account.code == "70117111").one()
    assert maize.analytic_allocations[0].activity.isacompta_code == "11171"
    # Règles de compte : 60111 → clé, 6155 → charges de structure.
    rules = {r.account_prefix: r for r in AnalyticRule.query.all()}
    assert rules["60111"].key_id == key.id
    assert next(r for p, r in rules.items() if p.startswith("6155")).activity_id == structure.id


def test_chosen_sections_only(farm):
    resp = _post(farm, "/api/v1/imports/isa", isa_file(), mode="history", start_date="2025-01-01",
                 end_date="2025-12-31", sections=json.dumps(["11171"]))
    body = resp.get_json()
    assert resp.status_code == 200, body
    assert {a.isacompta_code for a in Activity.query.all()} == {"11171"}
    assert body["analytic"]["rules"] == 1 and body["analytic"]["skipped"] == 1     # CS01 non reprise
    assert Workshop.query.count() == 1


def test_unbalanced_refused(farm):
    resp = _post(farm, "/api/v1/imports/isa", isa_file(unbalanced=True), mode="history", start_date="2025-01-01",
                 end_date="2025-12-31")
    assert resp.status_code == 409 and JournalEntry.query.count() == 0 and Activity.query.count() == 0


def test_not_agri_imports_entries_only(app, login_as):
    client = login_as(role="admin")
    resp = _post(client, "/api/v1/imports/isa", isa_file(), mode="history", start_date="2025-01-01", end_date="2025-12-31")
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["analytic"] == {} and Workshop.query.count() == 0
    assert Account.query.filter_by(code="60110000").one()                          # pas de reprise de l'ancien plan
