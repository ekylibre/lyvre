"""Restauration Ekylibre, lots RE1 à RE3 (claudedocs/design_restauration_ekylibre.md) : profils, référentiel détecté,
TVA conservée, noms de tiers rendus uniques, états des écritures (Q4), script générique, à-nouveaux (RE2),
pièces de la période, emprunt et TVA étrangère (RE3), agronomie et reclassement des stocks (RE4).
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
            (10, "44571000", "TVA collectée"), (11, "16400000", "Emprunt"), (12, "44575992", "TVA belge collectée")]


def extras_sql():
    """Lot RE3 : emprunt, vente à taux belge, pièces (facture d'achat, relevé, pièce de vente non reprise)."""
    return [
        copy_block("taxes", ["id", "name", "amount", "country", "nature", "collect_account_id"], [
            (1, "TVA 10", "10.0000", "fr", "intermediate_vat", 10), (2, "Belgian VAT normal", "21.0000", "be", "normal_vat", 12)]),
        copy_block("sale_items", ["id", "sale_id", "label", "quantity", "unit_pretax_amount", "pretax_amount", "amount",
                                  "account_id", "tax_id"], [
            (1, 1, "Vin", "1", "10.00", "10.00", "12.10", 9, 2), (2, 2, "Vin", "1", "10.00", "10.00", "11.00", 9, 1)]),
        copy_block("loans", ["id", "name", "amount", "started_on", "repayment_duration", "repayment_period",
                             "interest_percentage", "loan_account_id", "lender_id", "state"], [
            (1, "Emprunt tracteur", "1000.00", "2025-02-01", "10", "month", "2.0000", 11, 1, "ongoing")]),
        copy_block("loan_repayments", ["id", "loan_id", "position", "due_on", "amount", "remaining_amount"], [
            (1, 1, 1, "2025-11-01", "101.00", "900.00"), (2, 1, 2, "2025-12-01", "101.00", "800.00"),
            (3, 1, 3, "2026-01-01", "101.00", "700.00")]),
        copy_block("bank_statements", ["id", "cash_id", "number", "started_on", "stopped_on"], [
            (1, 1, "R1", "2025-03-01", "2025-03-31"), (2, 1, "R0", "2024-03-01", "2024-03-31")]),
        copy_block("attachments", ["id", "resource_type", "resource_id", "document_id", "deleted_at"], [
            (1, "Purchase", 1, 7, None), (2, "BankStatement", 1, 8, None), (3, "BankStatement", 2, 9, None),
            (4, "Sale", 1, 10, None)]),
        copy_block("documents", ["id", "name", "file_file_name"], [
            (7, "Facture", "semences.pdf"), (8, "Relevé", "releve-2025-03.pdf"), (9, "Relevé", "releve-2024-03.pdf"),
            (10, "Facture V1", "V1.pdf")]),
    ]


def agronomy_sql():
    """Lot RE4 : activités, cultures, campagnes, inventaire 2025 passé en comptabilité (ancien plan agricole)."""
    return [
        copy_block("accounts", ["id", "number", "name"], [(13, "37600000", "Vin bouteille"), (14, "71376000", "Variation vin")]),
        copy_block("journal_entries", ["id", "journal_id", "financial_year_id", "number", "state", "printed_on", "name"], [
            (20, 1, 2, "INV1", "draft", "2025-12-31", "Inventaire 2025")]),
        copy_block("journal_entry_items", ["id", "entry_id", "account_id", "name", "real_debit", "real_credit", "position"], [
            (40, 20, 13, "Stock", "500.00", "0.00", 1), (41, 20, 14, "Variation", "0.00", "500.00", 2)]),
        copy_block("activities", ["id", "name", "family", "nature", "production_cycle", "size_indicator_name",
                                  "size_unit_name", "suspended"], [
            (1, "Vignes", "vine_farming", "main", "perennial", "net_surface_area", "hectare", "f"),
            (2, "Blé", "plant_farming", "main", "annual", "net_surface_area", "hectare", "f"),
            (3, "Gestion", "administering", "auxiliary", "perennial", None, None, "f")]),
        copy_block("campaigns", ["id", "harvest_year"], [(1, 2025), (2, 2026)]),
        copy_block("activity_productions", ["id", "activity_id", "campaign_id", "started_on", "stopped_on", "size_value", "state"], [
            (1, 1, None, "2010-11-01", "2040-10-31", "2.5000", "opened"), (2, 1, None, "2026-11-01", "2050-10-31", "1.0000", "opened"),
            (3, 2, 1, "2024-10-01", "2025-08-31", "1.2000", "opened"), (4, 2, 2, "2025-10-01", "2026-08-31", "0.5000", "opened")]),
        copy_block("product_nature_categories", ["id", "name", "stock_account_id", "stock_movement_account_id"], [(1, "Vin", 13, 14)]),
        copy_block("product_nature_variants", ["id", "name", "unit_name", "default_unit_name"], [(1, "Bouteille 75 cl", "Unité", "unity"),
                                                                                                 (2, "Vrac", "Hl", "liter")]),
        copy_block("products", ["id", "name", "variant_id", "category_id"], [(1, "Cuvée 2024 75 cl", 1, 1), (2, "Vrac 2024", 2, 1)]),
        copy_block("inventories", ["id", "name", "financial_year_id", "reflected", "journal_entry_id", "product_nature_category_id"], [
            (1, "2025 - Vin", 2, "t", 20, 1)]),
        copy_block("inventory_items", ["id", "inventory_id", "product_id", "actual_population", "unit_pretax_stock_amount"], [
            (1, 1, 1, "100.0000", "5.0000"), (2, 1, 2, "0.0000", "90.0000")]),
    ]


def build_sql(legal=None, extras=False, agronomy=False):
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
        *(extras_sql() if extras else []),
        *(agronomy_sql() if agronomy else []),
    ]) + "\n"


def _archive(tmp_path, legal=None, extras=False, agronomy=False):
    path = tmp_path / f"ferme-{legal or 'x'}{'-plus' if extras else ''}{'-agro' if agronomy else ''}.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("ferme.sql", build_sql(legal, extras, agronomy))
        if extras:
            for doc, content in ((7, b"%PDF-1.4 facture"), (8, b"%PDF-1.4 releve"), (9, b"%PDF-1.4 ancien"), (10, b"%PDF-1.4 vente")):
                zf.writestr(f"files/attachments/documents/000/000/{doc:03d}/original.pdf", content)
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


def test_period_documents_loan_and_foreign_vat(app, tmp_path, monkeypatch):
    """Lot RE3 : pièces de la période (Q8), emprunt et TVA étrangère (D-R3) au rapport."""
    from app.extensions import db
    from app.models import Account, Purchase, SaleLine
    from app.models.bank_statement import BankStatement
    from app.services.ekylibre import importer
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    for code, label in (("101", "Capital"), ("164", "Emprunts"), ("401", "Fournisseurs"), ("411", "Clients"),
                        ("445", "État TVA"), ("512", "Banque"), ("601", "Achats"), ("701", "Ventes")):
        db.session.add(Account(code=code, label=label, account_type="OTHER", is_header=True))
    db.session.commit()
    archive = _archive(tmp_path, extras=True)
    data = _data(archive)
    std = profile.standard(data)
    assert std.attachments_from == 2025                                       # Q8 : 1re année reprise
    data.set_period(std.start, std.until)
    chart = Chart.from_database()
    plan = report.plan(data, chart, std)
    with open_source(archive) as source:
        ctx = importer.run(data, plan["accounts"], plan["entities"], chart, source=source,
                           attachments_from=std.attachments_from, profile=std)
    db.session.commit()
    assert Purchase.query.one().attachment_name == "semences.pdf"
    statement = BankStatement.query.one()                                     # 2024 hors période : non repris
    assert (statement.period, statement.source, statement.file_name) == (date(2025, 3, 1), "ekylibre", "releve-2025-03.pdf")
    assert ctx.stats["statement_files"] == 1 and ctx.stats["attachments"] == 1
    assert any("1 pièce(s) de vente" in n for n in ctx.notes)
    assert sorted(l.vat_rate_bp for l in SaleLine.query) == [1000, 2100]
    text = report.render(data, plan, [], str(archive), dry_run=False, imported=ctx, profile=std)
    loans = text.split("## Emprunts")[1].split("##")[0]
    assert "Emprunt tracteur" in loans and "| 10 mois |" in loans and "| 2 / 3 | 0 / 2 | 800,00 € |" in loans
    assert "⚠️" in loans                                                      # échéances échues non passées
    oss = text.split("## TVA étrangère des ventes (OSS)")[1].split("##")[0]
    assert "| BE | 21 % | 1 | 10,00 € | 2,10 € | 44575992 |" in oss and "| FR" not in oss
    assert "Relevé 03/2025 — Banque" in text


def test_agronomy_inventory_and_stock_reclass(app, tmp_path):
    """Lot RE4 : activités, campagnes, surfaces, dernier inventaire sans écriture, comptes de stock reclassés."""
    from app.extensions import db
    from app.models import Account, Activity, ActivityProduction, Campaign, JournalEntry, StockLine
    from app.services.ekylibre import importer
    for code, label, header in (("101", "Capital", True), ("164", "Emprunts", True), ("401", "Fournisseurs", True),
                                ("411", "Clients", True), ("445", "État TVA", True), ("512", "Banque", True),
                                ("601", "Achats", True), ("701", "Ventes", True), ("355", "Produits finis", True),
                                ("35513", "Produits finis transformés", False), ("713", "Variation", True),
                                ("71355", "Produits finis", False)):
        db.session.add(Account(code=code, label=label, account_type="OTHER", is_header=header))
    db.session.commit()
    archive = _archive(tmp_path, agronomy=True)
    data = _data(archive)
    std = profile.standard(data)
    assert std.stock_reclass and std.agronomy == profile.AGRONOMY
    data.set_period(std.start, std.until)
    chart = Chart.from_database()
    plan = report.plan(data, chart, std)
    assert (plan["accounts"]["37600000"].code, plan["accounts"]["37600000"].action) == ("35513", "reclass")
    assert plan["accounts"]["71376000"].code == "71355"
    ctx = importer.run(data, plan["accounts"], plan["entities"], chart, profile=std)
    db.session.commit()
    inv = JournalEntry.query.filter_by(source_ref="INV1").one()
    assert sorted((l.account.code, l.debit_cents, l.credit_cents) for l in inv.lines) == [("35513", 50000, 0), ("71355", 0, 50000)]
    assert inv.source != "STOCK"                                              # D-R2 révisé : rien de marqué
    vines = Activity.query.filter_by(ekylibre_id=1).one()
    assert (vines.unit, vines.cycle, vines.workshop.family) == ("hectare", "perennial", "vine_farming")
    assert Activity.query.filter_by(ekylibre_id=3).one().unit == "unity"
    assert [c.year for c in Campaign.query.order_by(Campaign.year)] == [2025]
    measures = {(p.activity.name, p.campaign.year): (float(p.measure), p.measure_source) for p in ActivityProduction.query}
    assert measures == {("Vignes", 2025): (2.5, "ekylibre"), ("Blé", 2025): (1.2, "ekylibre")}
    line = StockLine.query.one()                                              # article compté à zéro : écarté
    assert (line.account.code, line.variation_account.code, float(line.quantity), line.unit, line.value_cents) == (
        "35513", "71355", 100.0, "unit", 50000)
    assert ctx.stats["stock_lines"] == 1 and any("compté(s) à zéro" in n for n in ctx.notes)
    text = report.render(data, plan, [], str(archive), dry_run=False, imported=ctx, profile=std)
    assert "## Reclassement des comptes de stock" in text and "| 37600000 | Vin bouteille | 35513 |" in text
    assert "| Vignes | vine_farming | main | perennial | 2,50 |" in text
    assert "| 35513 (37600000) | 500,00 € | 500,00 € | 0,00 € |" in text               # inventaire = solde : neutre
