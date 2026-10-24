"""Reprise Ekylibre, lot K1 : lecture du dump, filtres de période, contrôles, correspondances, rapport,
analyse à blanc. Mini-dump fabriqué (aucune donnée réelle)."""
import io
import zipfile
from datetime import date

import pytest

from app.services.ekylibre import checks, report
from app.services.ekylibre.data import EkyData, cents
from app.services.ekylibre.mapping import Chart, map_accounts, map_journal, strip_zeros
from app.services.ekylibre.reader import iter_copy, open_source, unescape


def copy_block(table, columns, rows):
    lines = [f'COPY "tenant-x".{table} ({", ".join(columns)}) FROM stdin;']
    for row in rows:
        lines.append("\t".join("\\N" if v is None else str(v) for v in row))
    return "\n".join(lines + ["\\.", ""])


ACCOUNTS = [  # id, number, name
    (1, "10130000", "Capital"), (2, "11900000", "Report à nouveau"), (3, "12900000", "Résultat (perte)"),
    (4, "21310000", "Bâtiments"), (5, "40100000007", "EDF"), (6, "45510100", "CC Alice"), (7, "45510200", "CC Bob"),
    (8, "51201000", "Banque"), (9, "60613000", "Électricité"), (10, "44566004", "TVA 20 %"), (11, "70800000", "Loyers"),
    (12, "41100000003", "Locataire"), (13, "51101000", "Banque attente"),
]


def build_sql():
    blocks = [
        copy_block("financial_years", ["id", "code", "started_on", "stopped_on", "state"], [
            (1, "EX2024", "2024-01-01", "2024-12-31", "closed"), (2, "EX2025", "2025-01-01", "2025-12-31", "opened"),
            (3, "EX2026", "2026-01-01", "2026-12-31", "opened")]),
        copy_block("journals", ["id", "code", "name", "nature"], [
            (1, "BANQ", "Banque", "bank"), (2, "ACHA", "Achats", "purchases"), (3, "RG", "Reports", "forward"),
            (4, "CL", "Clôture", "closure"), (5, "CCAL", "CC Alice", "various"), (6, "VENT", "Ventes", "sales")]),
        copy_block("accounts", ["id", "number", "name"], ACCOUNTS),
        copy_block("entities", ["id", "full_name", "nature", "supplier", "client", "supplier_account_id",
                                "client_account_id", "siret_number", "vat_number", "iban"], [
            (1, "EDF", "organization", "t", "f", 5, None, "55208131766522", "FR03552081317", None),
            (2, "Alice", "contact", "f", "f", None, None, None, None, None),
            (3, "Bob", "contact", "f", "f", None, None, None, None, None),
            (4, "Locataire SARL", "organization", "f", "t", None, 12, None, None, None)]),
        copy_block("entity_addresses", ["id", "entity_id", "canal", "by_default", "deleted_at", "mail_line_1",
                                        "mail_line_2", "mail_line_6"], [
            (1, 1, "mail", "t", None, "EDF", "22-30 avenue de Wagram", "75008 PARIS"),
            (2, 1, "email", "f", None, "x@edf.fr", None, None)]),
        copy_block("journal_entries", ["id", "journal_id", "financial_year_id", "number", "state", "printed_on", "name",
                                       "resource_type", "resource_id"], [
            (1, 1, 1, "BANQ000001", "closed", "2024-06-01", "Apport", None, None),
            (2, 4, 1, "CL000001", "closed", "2024-12-31", "Clôture", None, None),
            (3, 3, 2, "RG000001", "confirmed", "2025-01-01", "À-nouveaux", None, None),
            (4, 2, 2, "ACHA000001", "draft", "2025-03-10", "Facture EDF", "Purchase", 1),
            (5, 1, 2, "BANQ000002", "draft", "2025-03-20", "PRELEVEMENT EDF", None, None),
            (6, 1, 3, "BANQ000003", "draft", "2026-07-10", "PRELEVEMENT EDF juillet", None, None),
            (7, 6, 2, "VENT000001", "draft", "2025-04-01", "Loyer avril", "Sale", 1),
            (8, 1, 2, "BANQ000004", "draft", "2025-04-10", "VIR LOCATAIRE", None, None),
            (9, 1, 1, "BANQ000000", "closed", "2024-01-01", "Apport de l'immeuble", None, None)]),
        copy_block("journal_entry_items", ["id", "entry_id", "account_id", "name", "real_debit", "real_credit",
                                           "letter", "position"], [
            (1, 1, 8, "Apport", "1000.00", "0.00", None, 1), (2, 1, 6, "Apport", "0.00", "1000.00", None, 2),
            (3, 2, 8, "Clôture", "0.00", "1000.00", None, 1), (4, 2, 6, "Clôture", "1000.00", "0.00", None, 2),
            (5, 3, 8, "AN", "1000.00", "0.00", None, 1), (6, 3, 6, "AN", "0.00", "1000.00", None, 2),
            (14, 3, 4, "AN", "1000.00", "0.00", None, 3), (15, 3, 1, "AN", "0.00", "1000.00", None, 4),
            (7, 4, 9, "Électricité", "100.00", "0.00", None, 1), (8, 4, 10, "TVA", "20.00", "0.00", None, 2),
            (9, 4, 5, "EDF", "0.00", "120.00", "A", 3),
            (10, 5, 5, "EDF", "120.00", "0.00", "A", 1), (11, 5, 8, "EDF", "0.00", "120.00", None, 2),
            (12, 6, 5, "EDF", "50.00", "0.00", None, 1), (13, 6, 8, "EDF", "0.00", "50.00", None, 2),
            (16, 7, 12, "Loyer", "500.00", "0.00", "B", 1), (17, 7, 11, "Loyer", "0.00", "500.00", None, 2),
            (18, 8, 8, "VIR", "500.00", "0.00", None, 1), (19, 8, 12, "VIR", "0.00", "500.00", "B", 2),
            (20, 9, 4, "Immeuble", "1000.00", "0.00", None, 1), (21, 9, 1, "Capital", "0.00", "1000.00", None, 2)]),
        copy_block("outgoing_payments", ["id", "number", "amount", "paid_at", "cash_id", "journal_entry_id", "affair_id",
                                         "payee_id"], [(1, "OP1", "120.00", "2025-03-20", 1, 5, 1, 1)]),
        copy_block("sales", ["id", "number", "client_id", "state", "credit", "invoiced_at", "created_at", "amount",
                             "pretax_amount", "journal_entry_id", "affair_id", "payment_at"], [
            (1, "V001", 4, "invoice", "f", "2025-04-01 00:00:00", "2025-04-01 00:00:00", "500.00", "500.00", 7, 2,
             "2025-04-30 00:00:00"),
            (2, "V002", 4, "draft", "f", None, "2026-01-16 00:00:00", "300.00", "300.00", None, 3, None)]),
        copy_block("sale_items", ["id", "sale_id", "label", "quantity", "unit_pretax_amount", "pretax_amount", "amount",
                                  "account_id"], [(1, 1, "Loyer avril", "1.0", "500.00", "500.00", "500.00", 11),
                                                  (2, 2, "Loyer", "1.0", "300.00", "300.00", "300.00", 11)]),
        copy_block("incoming_payment_modes", ["id", "name", "cash_id"], [(1, "virement", 1)]),
        copy_block("incoming_payments", ["id", "number", "amount", "paid_at", "mode_id", "journal_entry_id", "affair_id",
                                         "payer_id"], [(1, "IP1", "500.00", "2025-04-10", 1, 8, 2, 4)]),
        copy_block("purchases", ["id", "supplier_id", "number", "reference_number", "amount", "pretax_amount",
                                 "invoiced_at", "journal_entry_id", "tax_payability", "affair_id"], [
            (1, 1, "A001", "FAC-1", "120.00", "100.00", "2025-03-10 00:00:00", 4, "at_invoicing", 1)]),
        copy_block("purchase_items", ["id", "purchase_id", "account_id", "label", "pretax_amount", "amount"], [
            (1, 1, 9, "Électricité", "100.00", "120.00")]),
        copy_block("cashes", ["id", "name", "nature", "main_account_id", "journal_id"], [(1, "Banque", "bank_account", 8, 1)]),
        copy_block("bank_statements", ["id", "cash_id", "started_on", "stopped_on"], [(1, 1, "2024-01-01", "2026-12-31")]),
        copy_block("bank_statement_items", ["id", "bank_statement_id", "name", "debit", "credit", "transfered_on",
                                            "journal_entry_id", "letter"], [
            (1, 1, "Apport", "0.00", "1000.00", "2024-06-01", 1, "A"),
            (2, 1, "PRELEVEMENT EDF FACTURE 2025-03", "120.00", "0.00", "2025-03-20", 5, "B"),
            (3, 1, "VIR LOCATAIRE SARL LOYER", "0.00", "500.00", "2025-04-10", 8, "C")]),
        copy_block("attachments", ["id", "resource_type", "resource_id", "document_id", "deleted_at"], [
            (1, "Purchase", 1, 7, None)]),
        copy_block("documents", ["id", "name", "file_file_name", "file_content_text"], [
            (7, "Facture EDF", "edf.pdf", "EDF SA\\nSIRET 552 081 317 66522\\nTotal 120,00")]),
        copy_block("associates", ["id", "entity_id", "share_quantity", "share_unit_amount", "associate_nature",
                                  "started_on", "associate_account_id"], [
            (1, 2, "60", "10.00", "owner", "2019-01-01", 6), (2, 3, "40", "10.00", "owner", "2019-01-01", 7)]),
        copy_block("fixed_assets", ["id", "name", "depreciable_amount", "depreciation_method", "started_on",
                                    "asset_account_id", "state"], [(1, "Maison", "800.00", "none", "2019-01-01", 4, "in_use"),
                                                                   (2, "Terres", "200.00", "none", "2019-01-01", 4, "in_use")]),
    ]
    return "-- dump fabriqué pour les tests\n" + "\n".join(blocks)


@pytest.fixture()
def archive(tmp_path):
    path = tmp_path / "export.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("tenant-x.sql", build_sql())
        zf.writestr("files/attachments/documents/000/000/007/original.pdf", b"%PDF-1.4 facture")
    return path


def load(archive, until=date(2026, 6, 30)):
    with open_source(archive) as source:
        return EkyData.load(source, date(2025, 1, 1), until)


def test_reader_unescape_and_blocks():
    assert unescape(r"\N") is None and unescape(r"a\tb\\c") == "a\tb\\c" and unescape(r"l1\nl2") == "l1\nl2"
    rows = list(iter_copy(io.StringIO(build_sql()), {"accounts"}))
    assert len(rows) == len(ACCOUNTS) and rows[0] == ("accounts", {"id": "1", "number": "10130000", "name": "Capital"})


def test_source_zip_and_folder(archive, tmp_path):
    with open_source(archive) as source:
        assert source.document_file(7) == ("original.pdf", b"%PDF-1.4 facture")
        assert source.document_file(8) is None
    folder = tmp_path / "extrait"
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(folder)
    with open_source(folder) as source:
        assert source.document_file("7")[1].startswith(b"%PDF")


def test_period_filters(archive):
    data = load(archive)
    assert [e["number"] for e in data.entries()] == ["RG000001", "ACHA000001", "BANQ000002", "VENT000001", "BANQ000004"]
    assert [e["number"] for e in data.entries_after()] == ["BANQ000003"]
    assert len(data.purchases()) == 1 and len(data.statement_items()) == 2 and len(data.sales()) == 2
    assert cents("1234.565") == 123457 and data.documents_of("Purchase", "1")[0]["id"] == "7"


def test_checks(archive):
    results = {c.key: c for c in checks.run(load(archive))}
    assert results["balanced"].ok and results["opening"].ok
    assert results["bank_1"].ok  # 1 000 − 120 + 500 des deux côtés
    assert "20.00 €" in results["vat"].label and results["associates"].ok  # 100 parts × 10 € = capital
    assert results["after"].details and "BANQ000003" in results["after"].details[0]


def test_account_mapping(archive):
    data = load(archive)
    chart = Chart({"101": ("Capital", True), "1013": ("Capital appelé versé", False), "401": ("Fournisseurs", True),
                   "512": ("Banque", True), "6061": ("Fournitures", True), "60613": ("Électricité", False)})
    targets = map_accounts(data, chart, {a[1] for a in ACCOUNTS})
    assert (targets["40100000007"].code, targets["40100000007"].label, targets["40100000007"].action) == ("401007", "EDF", "create")
    assert targets["45510100"].code == "4551001" and targets["45510200"].code == "4551002"
    assert (targets["10130000"].code, targets["10130000"].action) == ("1013", "existing")
    assert (targets["60613000"].code, targets["60613000"].action) == ("60613", "existing")
    assert (targets["51201000"].code, targets["51201000"].parent) == ("51201", "512")
    assert targets["44566004"].action == "vat"
    assert strip_zeros("40100000") == "401" and map_journal("CCAL") == "AS" and map_journal("RG") == "AN"


def test_report_and_dry_run_script(archive, tmp_path):
    data = load(archive)
    mapping = report.plan(data, Chart.from_file())
    text = report.render(data, mapping, checks.run(data), str(archive), dry_run=True)
    assert "analyse à blanc" in text and "| 40100000007 | EDF | 401007 |" in text
    assert "22-30 avenue de Wagram" not in text and "PARIS" in text  # ville au rapport, pas l'adresse
    from importlib import util
    spec = util.spec_from_file_location("import_ekylibre_sci", "scripts/import_ekylibre_sci.py")
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    out = tmp_path / "rapport.md"
    code = module.main([str(archive), "--dry-run", "--report", str(out)])
    assert code == 0 and out.read_text(encoding="utf-8").startswith("# Rapport de reprise")
    with pytest.raises(SystemExit):
        module.main([str(archive)])  # import sans --meta-url : refusé


# ------------------------------------------------------------------ lot K2 : import dans la base courante


def _mini_chart():
    from app.extensions import db
    from app.models import Account
    for code, label, header in (("101", "Capital", True), ("11", "Report", True), ("12", "Résultat", True),
                                ("213", "Constructions", True), ("401", "Fournisseurs", True), ("411", "Clients", True),
                                ("445", "État TVA", True), ("455", "Associés", True), ("512", "Banque", True), ("211", "Terrains", True),
                                ("511", "Valeurs à l'encaissement", True), ("6061", "Fournitures", True),
                                ("60613", "Électricité", False), ("708", "Produits annexes", True)):
        db.session.add(Account(code=code, label=label, account_type="OTHER", is_header=header))
    db.session.commit()


def _import(archive):
    from app.services.ekylibre import importer, report
    from app.services.ekylibre.mapping import Chart
    data = load(archive)
    chart = Chart.from_database()
    plan = report.plan(data, chart)
    return importer.run(data, plan["accounts"], plan["entities"], chart)


def test_import_entries_vat_states_lettering_associates(app, archive):
    _mini_chart()
    from app.extensions import db
    from app.models import Account, Associate, JournalEntry, Lettering, ShareMovement
    ctx = _import(archive)
    db.session.commit()
    assert ctx.stats["entries"] == 5 and JournalEntry.query.count() == 6  # + reclassement des terrains
    purchase = JournalEntry.query.filter_by(source_ref="ACHA000001").one()
    assert sorted((l.account.code, l.debit_cents, l.credit_cents) for l in purchase.lines) == [
        ("401007", 0, 12000), ("60613", 12000, 0)]  # TVA intégrée à la charge (EK3)
    assert ctx.vat_corrections == [("ACHA000001", 2000)]
    opening = JournalEntry.query.filter_by(source_ref="RG000001").one()
    assert opening.source == "OPENING" and opening.journal.code == "AN" and opening.is_validated
    assert not purchase.is_validated and purchase.journal.code == "AC"
    letters = {l.account.code: l for l in Lettering.query.all()}
    assert letters["401007"].code == "A" and not letters["401007"].partial and letters["411003"].code == "B"
    assert Associate.query.count() == 2 and ShareMovement.query.one().kind == "opening"
    assert Account.query.filter_by(code="4551001").one().label == "Compte courant — Alice"
    assert Account.query.filter_by(code="51201").one().parent.code == "512"


def test_import_refuses_unknown_account(app, archive):
    _mini_chart()
    from app.services.ekylibre import importer, report
    from app.services.ekylibre.mapping import Chart
    data = load(archive)
    chart = Chart.from_database()
    plan = report.plan(data, chart)
    plan["accounts"].pop("60613000")
    with pytest.raises(importer.ImportFailure):
        importer.run(data, plan["accounts"], plan["entities"], chart)


def test_import_bank_documents_assets(app, archive, tmp_path, monkeypatch):
    _mini_chart()
    from app.extensions import db
    from app.models import Asset, BankTransaction, JournalEntry, Purchase, Sale, SalePayment
    from app.services.ekylibre import importer, report
    from app.services.ekylibre.mapping import Chart
    monkeypatch.setattr(app, "instance_path", str(tmp_path))
    data = load(archive)
    chart = Chart.from_database()
    plan = report.plan(data, chart)
    with open_source(archive) as source:
        ctx = importer.run(data, plan["accounts"], plan["entities"], chart, source=source, attachments_from=2025)
    db.session.commit()
    txns = BankTransaction.query.order_by(BankTransaction.transaction_date).all()
    assert [(t.amount_cents, t.reconciled, t.source) for t in txns] == [(-12000, True, "ekylibre"), (50000, True, "ekylibre")]
    purchase = Purchase.query.one()
    assert (purchase.source, purchase.total_cents, purchase.tax_cents, purchase.invoice_number) == ("ekylibre", 12000, 0, "FAC-1")
    assert [l.total_cents for l in purchase.lines] == [12000] and purchase.journal_entry_id
    (payment,) = purchase.payments
    assert payment.origin == "match" and payment.bank_transaction_id == txns[0].id
    stored = tmp_path / "uploads" / "default" / purchase.attachment_path  # hors requête : dossier « default »
    assert stored.read_bytes() == b"%PDF-1.4 facture" and purchase.attachment_name == "edf.pdf"
    invoice = Sale.query.filter_by(number="V001").one()
    assert invoice.status == "paid" and SalePayment.query.one().bank_transaction_id == txns[1].id
    assert Sale.query.filter_by(status="draft").one().number is None
    assets = {a.label: a.account.code for a in Asset.query.all()}
    assert assets == {"Maison": "2131", "Terres": "211000"}
    reclass = JournalEntry.query.filter_by(source_ref="RECLASSEMENT-TERRAINS").one()
    assert sorted((l.account.code, l.debit_cents, l.credit_cents) for l in reclass.lines) == [("211000", 20000, 0), ("2131", 0, 20000)]
    assert ctx.stats["attachments"] == 1 and not reclass.is_validated
