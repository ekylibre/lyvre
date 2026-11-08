"""Saisies en brouillon par clé d'API (lot AK3, claudedocs/design_api_mcp_aiffel.md § 7, récits 3 et 4)."""
import base64
from datetime import date

import fitz
import pytest

from app.extensions import db
from app.models import Account, ApiCall, Entity, FiscalYear, Journal, JournalEntry, Purchase
from app.services import purchase_posting


def _pdf(text: str) -> bytes:
    doc = fitz.open()
    doc.new_page().insert_text((60, 80), text, fontsize=11)
    return doc.tobytes()


TICKET = _pdf("COOP DU VAL\nFacture n° T-778\nDate de facture : 03/11/2026\nTotal HT 1 000,00 EUR\n"
              "TVA 20 % 200,00 EUR\nTotal TTC 1 200,00 EUR")


@pytest.fixture()
def farm(app, login_as):
    admin = login_as(role="admin")
    for code in ("401", "512", "6011", "6068", "44566", "411", "706"):
        db.session.add(Account(code=code, label=code, account_type="EXPENSE"))
    db.session.add_all([Journal(code="AC", label="Achats"), Journal(code="OD", label="Opérations diverses"),
                        FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31),
                                   vat_liable=True)])
    db.session.commit()

    def key(read=("purchases",), write=("purchases",)):
        res = admin.post("/api/v1/api-keys", json={"name": "Aiffel — terrain", "read_domains": list(read),
                                                   "write_domains": list(write)})
        assert res.status_code == 201, res.json
        return res.json["token"]
    return {"admin": admin, "key": key}


def call(app, token, name, arguments):
    res = app.test_client().post("/mcp", headers={"Authorization": f"Bearer {token}"}, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
    assert res.status_code == 200, res.data
    return res.json["result"]


def test_purchase_draft_is_never_posted_before_check(app, farm):
    token = farm["key"](write=("purchases", "parties"), read=("purchases", "parties"))
    res = call(app, token, "create_purchase_draft", {
        "supplier": {"name": "Coop du Val"}, "issue_date": "2026-11-03", "total": "1 200,00", "untaxed": 1000,
        "tax": "200", "invoice_number": "T-778", "note": "2 t d'engrais"})
    assert res["isError"] is False, res
    out = res["structuredContent"]
    assert out["created"] is True and "NON comptabilisé" in out["message"] and out["url"].endswith(f"/purchases/{out['purchase_id']}")
    p = db.session.get(Purchase, out["purchase_id"])
    assert p.journal_entry_id is None and p.origin_label == "Aiffel — terrain" and p.checked_at is None
    assert p.entity is not None and p.entity.origin_key_id is not None and p.entity.checked_at is None
    assert p.lines and p.lines[0].vat_rate_bp == 2000 and sum(l.total_cents for l in p.lines) == 120000
    assert "2 t d'engrais" in p.review_reason
    state = purchase_posting.purchase_state(p)
    assert state.code == "to_complete" and any("à vérifier" in r for r in state.reasons)
    assert p not in purchase_posting.ready_purchases()       # « Comptabiliser les prêtes » l'ignore
    # Tableau de bord et liste.
    assert farm["admin"].get("/api/v1/dashboard").json["agent"]["purchases"] == 1
    listing = farm["admin"].get("/api/v1/purchases?from_key=1").json
    assert [i["id"] for i in listing["items"]] == [p.id] and listing["items"][0]["origin"]["pending"] is True
    # Vérification humaine (récit 4) : comptabilisée car prête.
    checked = farm["admin"].post(f"/api/v1/purchases/{p.id}/check")
    assert checked.status_code == 200, checked.json
    db.session.refresh(p)
    assert p.checked_at is not None and p.journal_entry_id is not None
    assert db.session.get(JournalEntry, p.journal_entry_id).validation_number is None   # brouillard
    assert farm["admin"].get("/api/v1/dashboard").json["agent"]["purchases"] == 0


def test_supplier_not_created_without_parties_write(app, farm):
    token = farm["key"]()
    out = call(app, token, "create_purchase_draft", {"supplier": {"name": "Inconnu SARL"}, "issue_date": "2026-11-03",
                                                     "total": 50})["structuredContent"]
    p = db.session.get(Purchase, out["purchase_id"])
    assert p.entity is None and p.supplier_name == "Inconnu SARL"
    assert "Fournisseur non rattaché : à choisir dans Lyvre." in out["warnings"]
    assert Entity.query.count() == 0


def test_purchase_from_photo_reads_the_document(app, farm):
    token = farm["key"]()
    out = call(app, token, "create_purchase_draft", {
        "file": {"name": "bon.pdf", "content_base64": base64.b64encode(TICKET).decode()}})["structuredContent"]
    assert out.get("error") is None, out
    p = db.session.get(Purchase, out["purchase_id"])
    assert p.total_cents == 120000 and p.invoice_number == "T-778" and p.issue_date == date(2026, 11, 3)
    assert p.attachment_path and out["has_attachment"] is True


def test_idempotence(app, farm):
    token = farm["key"]()
    args = {"supplier": {"name": "Coop"}, "issue_date": "2026-11-03", "total": 10, "external_ref": "fourmy:intervention/12"}
    first = call(app, token, "create_purchase_draft", args)["structuredContent"]
    again = call(app, token, "create_purchase_draft", {**args, "total": 99})["structuredContent"]
    assert first["created"] is True and again["created"] is False and again["purchase_id"] == first["purchase_id"]
    by_key = {"supplier": {"name": "Coop"}, "issue_date": "2026-11-04", "total": 20, "idempotency_key": "essai-1"}
    one = call(app, token, "create_purchase_draft", by_key)["structuredContent"]
    two = call(app, token, "create_purchase_draft", by_key)["structuredContent"]
    assert two["created"] is False and two["purchase_id"] == one["purchase_id"]
    assert Purchase.query.count() == 2
    assert ApiCall.query.filter(ApiCall.object_id.isnot(None)).count() == 2


def test_refusals_leave_nothing(app, farm):
    token = farm["key"](write=())
    refused = call(app, token, "create_purchase_draft", {"issue_date": "2026-11-03", "total": 10})
    assert refused["isError"] is True and refused["structuredContent"]["code"] == "domain_forbidden"
    token = farm["key"]()
    bad = call(app, token, "create_purchase_draft", {"supplier": {"name": "X"}, "total": 10})
    assert bad["isError"] is True and "date de facture" in bad["structuredContent"]["error"].lower()
    assert Purchase.query.count() == 0 and Entity.query.count() == 0
    assert ApiCall.query.filter_by(status=422).count() == 1


def test_create_supplier(app, farm):
    token = farm["key"](read=("parties",), write=("parties",))
    out = call(app, token, "create_supplier", {"name": "Semences de l'Ouest", "siren": "123456789"})["structuredContent"]
    assert out["created"] is True and out["state"] == "à vérifier"
    again = call(app, token, "create_supplier", {"name": "Autre nom", "siren": "123456789"})["structuredContent"]
    assert again["created"] is False and again["party_id"] == out["party_id"]
    res = farm["admin"].post(f"/api/v1/tiers/{out['party_id']}/check")
    assert res.status_code == 200 and res.json["item"]["origin"]["pending"] is False


def test_entry_draft_is_not_validated(app, farm):
    token = farm["key"](read=("accounting",), write=("accounting",))
    out = call(app, token, "create_entry_draft", {"date": "2026-11-05", "label": "Frais", "lines": [
        {"account": "6068", "debit": "15,50"}, {"account": "512", "credit": "15,50"}]})["structuredContent"]
    assert out.get("error") is None, out
    entry = db.session.get(JournalEntry, out["entry_id"])
    assert entry.validation_number is None and entry.origin_label == "Aiffel — terrain"
    assert farm["admin"].get("/api/v1/dashboard").json["agent"]["entries"] == 1
    unbalanced = call(app, token, "create_entry_draft", {"date": "2026-11-05", "lines": [
        {"account": "6068", "debit": "15"}, {"account": "512", "credit": "14"}]})
    assert unbalanced["isError"] is True


def test_accountant_key_has_no_write_tools(app, farm):
    from app.models import ApiKey
    token = farm["key"](read=("purchases",), write=("purchases",))
    key = db.session.query(ApiKey).one()
    from app.models import InstanceMembership
    db.session.query(InstanceMembership).filter_by(user_id=key.user_id).update({"role": "accountant"})
    db.session.commit()
    names = {t["name"] for t in app.test_client().post("/mcp", headers={"Authorization": f"Bearer {token}"}, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json["result"]["tools"]}
    assert "list_purchases" in names and "create_purchase_draft" not in names


def test_rest_file_upload_then_draft(app, farm):
    token = farm["key"]()
    client = app.test_client()
    headers = {"Authorization": f"Bearer {token}"}
    import io
    up = client.post("/api/v1/agent/files", headers=headers, data={"file": (io.BytesIO(TICKET), "bon.pdf")},
                     content_type="multipart/form-data")
    assert up.status_code == 201, up.json
    res = client.post("/api/v1/agent/tools/create_purchase_draft", headers=headers, json={"file_token": up.json["file_token"]})
    assert res.status_code == 200, res.json
    assert res.json["result"]["has_attachment"] is True
    assert ApiCall.query.filter_by(channel="rest").count() == 1


def test_write_tools_never_post_validate_or_send():
    """Garde-fou (§ 11) : aucun outil d'écriture n'appelle la comptabilisation, la validation ou un envoi."""
    import inspect
    from app.services import agent_writes
    source = inspect.getsource(agent_writes)
    for forbidden in ("post_ready", "validate_entries", "validation.", "send_to_qonto", "superpdp", "send_invoice"):
        assert forbidden not in source, forbidden
