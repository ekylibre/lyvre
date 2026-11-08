"""Restauration Ekylibre, lots RE1 et RE2 (claudedocs/design_restauration_ekylibre.md) : profils, référentiel détecté,
TVA conservée, noms de tiers rendus uniques, états des écritures (Q4), script générique.
Mini-dump fabriqué d'une ferme assujettie (aucune donnée réelle)."""
import zipfile
from datetime import date
from importlib import util

import pytest

from app.services.ekylibre import checks, profile, report
from app.services.ekylibre.data import WIDE_START, WIDE_UNTIL, EkyData
from app.services.ekylibre.mapping import Chart, chart_file, map_accounts
from app.services.ekylibre.reader import open_source
from test_ekylibre_import import copy_block

ACCOUNTS = [(1, "10100000", "Capital"), (2, "40100000001", "Coop"), (3, "41100000002", "Sarah"),
            (4, "41100000003", "Sarah"), (5, "41100000004", "sarah"), (6, "60110000", "Semences"),
            (7, "44566000", "TVA déductible"), (8, "51200000", "Banque"), (9, "70100000", "Ventes vin"),
            (10, "44571000", "TVA collectée")]


def build_sql(legal=None):
    return "\n".join([
        copy_block("preferences", ["id", "name", "string_value", "user_id"], [
            (1, "accounting_system", "fr_pcga", None), (2, "fiscal_position", "fr_ba_ir", None)]),
        copy_block("financial_years", ["id", "code", "started_on", "stopped_on", "state", "closed",
                                       "tax_declaration_frequency", "tax_declaration_mode"], [
            (1, "EX2024", "2024-01-01", "2024-12-31", "locked", "f", "quaterly", "debit"),
            (2, "EX2025", "2025-01-01", "2025-12-31", "opened", "f", "quaterly", "payment")]),
        copy_block("journals", ["id", "code", "name", "nature"], [
            (1, "BANQ", "Banque", "bank"), (2, "ACHA", "Achats", "purchases"), (3, "VENT", "Ventes", "sales")]),
        copy_block("accounts", ["id", "number", "name"], ACCOUNTS),
        copy_block("entities", ["id", "number", "full_name", "nature", "supplier", "client", "supplier_account_id",
                                "client_account_id", "of_company", "vat_subjected", "legal_position_code"], [
            (1, "00000001", "Coop", "organization", "t", "f", 2, None, "f", None, None),
            (2, "00000002", "Sarah", "contact", "f", "t", None, 3, "f", None, None),
            (3, "00000003", "Sarah", "contact", "f", "t", None, 4, "f", None, None),
            (4, "00000004", "sarah", "contact", "f", "t", None, 5, "f", None, None),
            (9, "00000009", "Domaine d'essai", "organization", "f", "f", None, None, "t", "t", legal)]),
        copy_block("entity_addresses", ["id", "entity_id", "canal", "by_default", "deleted_at", "mail_line_6"], [
            (1, 2, "mail", "t", None, "69001 LYON")]),
        copy_block("journal_entries", ["id", "journal_id", "financial_year_id", "number", "state", "printed_on", "name"], [
            (1, 1, 1, "BANQ1", "draft", "2024-02-01", "Apport"),
            (2, 2, 2, "ACHA1", "draft", "2025-03-10", "Semences"),
            (3, 3, 2, "VENT1", "draft", "2025-04-01", "Vente Sarah"),
            (4, 3, 2, "VENT2", "confirmed", "2025-04-02", "Vente Sarah Lyon"),
            (5, 3, 2, "VENT3", "draft", "2025-04-03", "Vente sarah"),
            (6, 3, 1, "VENT0", "draft", "2024-06-01", "Vente 2024")]),
        copy_block("journal_entry_items", ["id", "entry_id", "account_id", "name", "real_debit", "real_credit", "position"], [
            (1, 1, 8, "Apport", "1000.00", "0.00", 1), (2, 1, 1, "Apport", "0.00", "1000.00", 2),
            (3, 2, 6, "Semences", "100.00", "0.00", 1), (4, 2, 7, "TVA", "20.00", "0.00", 2), (5, 2, 2, "Coop", "0.00", "120.00", 3),
            (6, 3, 3, "Sarah", "11.00", "0.00", 1), (7, 3, 9, "Vin", "0.00", "10.00", 2), (8, 3, 10, "TVA", "0.00", "1.00", 3),
            (9, 4, 4, "Sarah", "11.00", "0.00", 1), (10, 4, 9, "Vin", "0.00", "10.00", 2), (11, 4, 10, "TVA", "0.00", "1.00", 3),
            (12, 5, 5, "sarah", "11.00", "0.00", 1), (13, 5, 9, "Vin", "0.00", "10.00", 2), (14, 5, 10, "TVA", "0.00", "1.00", 3),
            (15, 6, 8, "Vente", "300.00", "0.00", 1), (16, 6, 9, "Vente", "0.00", "300.00", 2)]),
        copy_block("purchases", ["id", "supplier_id", "number", "amount", "pretax_amount", "invoiced_at", "journal_entry_id",
                                 "tax_payability"], [(1, 1, "A1", "120.00", "100.00", "2025-03-10 00:00:00", 2, "at_invoicing")]),
        copy_block("sales", ["id", "number", "client_id", "state", "credit", "invoiced_at", "created_at", "amount",
                             "pretax_amount", "journal_entry_id"], [
            (1, "V1", 2, "invoice", "f", "2025-04-01 00:00:00", "2025-04-01 00:00:00", "11.00", "10.00", 3),
            (2, "V2", 3, "invoice", "f", "2025-04-02 00:00:00", "2025-04-02 00:00:00", "11.00", "10.00", 4),
            (3, "V3", 4, "invoice", "f", "2025-04-03 00:00:00", "2025-04-03 00:00:00", "11.00", "10.00", 5)]),
        copy_block("cashes", ["id", "name", "nature", "main_account_id", "journal_id"], [(1, "Banque", "bank_account", 8, 1)]),
    ]) + "\n"


def _archive(tmp_path, legal=None):
    path = tmp_path / f"ferme-{legal or 'x'}.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ferme.sql", build_sql(legal))
    return path


@pytest.fixture()
def farm(tmp_path):
    return _archive(tmp_path)


def _data(farm):
    with open_source(farm) as source:
        return EkyData.load(source, WIDE_START, WIDE_UNTIL)


def test_standard_profile_is_detected_from_the_backup(farm):
    data = _data(farm)
    std = profile.standard(data)
    assert (std.chart, std.start, std.until) == ("agri", date(2025, 1, 1), date(2025, 12, 31))   # 1er exercice ouvert
    assert not std.absorb_purchase_vat and not std.land_reclass and std.validate_rule == "locked_years"
    assert profile.standard(data, all_history=True).start == date(2024, 1, 1)
    assert profile.standard(data, chart="societe").chart == "societe"
    sci = profile.sci()
    assert sci.is_sci and sci.absorb_purchase_vat and sci.land_reclass and sci.validate_rule == "confirmed"


def test_validation_rule_q4():
    std = profile.Profile(name="standard", chart="agri")
    assert std.should_validate({"state": "draft"}, {"state": "locked"})
    assert std.should_validate({"state": "confirmed"}, {"state": "opened"})
    assert not std.should_validate({"state": "draft"}, {"state": "opened"})
    assert not profile.sci().should_validate({"state": "draft"}, {"state": "locked"})   # EK2 inchangé


def test_vat_kept_and_names_made_unique(farm):
    data = _data(farm)
    std = profile.standard(data)
    data.set_period(std.start, std.until)
    targets = map_accounts(data, Chart.from_file(chart_file("agri")), {a[1] for a in ACCOUNTS}, absorb_vat=False)
    assert targets["44566000"].action != "vat"
    mapping = report.plan(data, Chart.from_file(chart_file("agri")), std)
    names = sorted(e.name for e in mapping["entities"].values())
    assert names == ["Coop", "Sarah (#00000003)", "Sarah (LYON)", "sarah (#00000004)"]
    results = {c.key: c for c in checks.run(data, std, mapping["entities"])}
    assert results["entity_names"].ok and len(results["entity_renamed"].details) == 3
    assert "conservée" in results["vat"].label and "opening" not in results
    assert results["states"].details == ["2025 brouillard : 3", "2025 validée : 1"]
    assert not {c.key: c for c in checks.run(data)}["entity_names"].ok   # sans dédoublonnage : bloquant


def test_restore_script_dry_run(farm, tmp_path):
    spec = util.spec_from_file_location("restore_ekylibre", "scripts/restore_ekylibre.py")
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = tmp_path / "rapport.md"
    assert module.main([str(farm), "--dry-run", "--report", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "Profil : **standard**, référentiel `agri`" in text and "du 01/01/2025 au 31/12/2025" in text
    assert "TVA déductible des achats intégrée" not in text and "## Corrections prévues\n\nAucune." in text
    assert module.main([str(farm), "--dry-run", "--all-history", "--report", str(out)]) == 0
    assert "du 01/01/2024 au 31/12/2025" in out.read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        module.main([str(farm), "--dry-run", "--from-year", "2019"])
    with pytest.raises(SystemExit):
        module.main([str(farm)])   # import sans --meta-url ni --slug : refusé


def test_import_keeps_vat_and_marks_the_year_vat_liable(app, farm):
    from app.extensions import db
    from app.models import Account, FiscalYear, JournalEntry
    from app.services.ekylibre import importer
    for code, label in (("101", "Capital"), ("401", "Fournisseurs"), ("411", "Clients"), ("445", "État TVA"),
                        ("512", "Banque"), ("601", "Achats"), ("701", "Ventes")):
        db.session.add(Account(code=code, label=label, account_type="OTHER", is_header=True))
    db.session.commit()
    data = _data(farm)
    std = profile.standard(data)
    data.set_period(std.start, std.until)
    chart = Chart.from_database()
    plan = report.plan(data, chart, std)
    ctx = importer.run(data, plan["accounts"], plan["entities"], chart, profile=std)
    db.session.commit()
    purchase = JournalEntry.query.filter_by(source_ref="ACHA1").one()
    assert sorted((l.account.code, l.debit_cents, l.credit_cents) for l in purchase.lines) == [
        ("401001", 0, 12000), ("44566", 2000, 0), ("6011", 10000, 0)]          # TVA conservée
    assert ctx.vat_corrections == [] and FiscalYear.query.one().vat_liable
    assert JournalEntry.query.filter_by(source_ref="VENT2").one().is_validated     # confirmée
    assert not purchase.is_validated
    assert Account.query.filter_by(code="44566").one().parent.code == "445"
    fy = FiscalYear.query.one()
    assert (fy.vat_period, fy.vat_on_receipts) == ("quarterly", True)                # lot RE2 : réglages de TVA
    opening = JournalEntry.query.filter_by(source_ref="AN-EKYLIBRE").one()           # à-nouveaux calculés
    assert opening.entry_date == date(2025, 1, 1) and opening.source == "OPENING" and opening.is_validated  # 2024 verrouillé
    assert sorted((l.account.code, l.debit_cents, l.credit_cents) for l in opening.lines) == [
        ("101000", 0, 100000), ("12", 0, 30000), ("512000", 130000, 0)]
    assert any("Forme juridique absente" in n for n in ctx.notes)


def _import_with(app, archive):
    from app.extensions import db
    from app.models import Account
    from app.services.ekylibre import importer
    for code, label in (("101", "Capital"), ("108", "Exploitant"), ("11", "Report"), ("110", "RAN créditeur"),
                        ("119", "RAN débiteur"), ("12", "Résultat"), ("120", "Bénéfice"), ("129", "Perte"),
                        ("401", "Fournisseurs"), ("411", "Clients"), ("445", "État TVA"), ("512", "Banque"),
                        ("601", "Achats"), ("701", "Ventes")):
        db.session.add(Account(code=code, label=label, account_type="OTHER", is_header=code in ("101", "11", "401", "411", "445", "512", "601", "701")))
    db.session.commit()
    data = _data(archive)
    std = profile.standard(data)
    data.set_period(std.start, std.until)
    chart = Chart.from_database()
    plan = report.plan(data, chart, std)
    return importer.run(data, plan["accounts"], plan["entities"], chart, profile=std)


def test_opening_follows_the_legal_form(app, tmp_path):
    from app.models import JournalEntry
    ctx = _import_with(app, _archive(tmp_path, "EI"))
    lines = {l.account.code: l.credit_cents for l in JournalEntry.query.filter_by(source_ref="AN-EKYLIBRE").one().lines}
    assert lines["108"] == 30000 and "12" not in lines                                   # D-R1 : exploitant
    assert ctx.stats["opening_lines"] == 3


def test_opening_of_a_company(app, tmp_path):
    from app.models import JournalEntry
    _import_with(app, _archive(tmp_path, "EARL"))
    lines = {l.account.code: l.credit_cents for l in JournalEntry.query.filter_by(source_ref="AN-EKYLIBRE").one().lines}
    assert lines["120"] == 30000 and "110" not in lines                                  # bénéfice 2024 à affecter


def test_opening_check_and_cumulative_control(farm):
    from app.services.ekylibre import importer
    data = _data(farm)
    std = profile.standard(data)
    data.set_period(std.start, std.until)
    mapping = report.plan(data, Chart.from_file(chart_file("agri")), std)
    assert mapping["opening"].balances == {"51200000": 130000, "10100000": -100000}
    results = {c.key: c for c in checks.run(data, std, mapping["entities"])}
    assert results["opening_computed"].ok and "12 Résultat de l'exercice : -300.00 €" in results["opening_computed"].details
    assert importer.compare_balances.__doc__ and "RE-C6" in importer.compare_balances.__doc__
