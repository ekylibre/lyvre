"""Journal des appels, limites et aide des clés d'API (lot AK4, claudedocs/design_api_mcp_aiffel.md § 8, récits 5 et 7)."""
from datetime import date, datetime, timedelta

import pytest

from app.extensions import db
from app.models import ApiCall, ApiKey, FiscalYear


@pytest.fixture()
def admin(app, login_as):
    client = login_as(role="admin")
    db.session.add(FiscalYear(label="2026", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)))
    db.session.commit()
    return client


def _key(admin, **body):
    payload = {"name": "Aiffel", "read_domains": ["purchases"], "write_domains": ["purchases"], **body}
    res = admin.post("/api/v1/api-keys", json=payload)
    assert res.status_code == 201, res.json
    return res.json["token"], res.json["item"]["id"]


def _get(app, token, path="/api/v1/purchases"):
    return app.test_client().get(path, headers={"Authorization": f"Bearer {token}"})


def _tool(app, token, name, arguments):
    return app.test_client().post("/mcp", headers={"Authorization": f"Bearer {token}"}, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}})


def test_rate_limit_rest_and_mcp(app, admin):
    token, key_id = _key(admin, rate_per_minute=2)
    assert _get(app, token).status_code == 200
    assert _get(app, token).status_code == 200
    res = _get(app, token)
    assert res.status_code == 429 and int(res.headers["Retry-After"]) >= 1
    assert res.json["error"]["code"] == "rate_limited" and "2 par minute" in res.json["error"]["message"]
    mcp = _tool(app, token, "list_purchases", {})
    assert mcp.status_code == 429 and mcp.json["error"]["code"] == -32000 and mcp.json["error"]["data"]["retry_after"] >= 1
    assert ApiCall.query.filter_by(key_id=key_id, status=429).count() == 2


def test_daily_creation_cap_keeps_reading(app, admin):
    token, key_id = _key(admin, creations_per_day=1)
    args = {"supplier": {"name": "Coop"}, "issue_date": "2026-11-03", "total": 10}
    assert _tool(app, token, "create_purchase_draft", args).json["result"]["isError"] is False
    refused = _tool(app, token, "create_purchase_draft", {**args, "total": 11}).json["result"]
    assert refused["isError"] is True and refused["structuredContent"]["code"] == "daily_cap"
    assert _tool(app, token, "list_purchases", {}).json["result"]["isError"] is False
    rest = app.test_client().post("/api/v1/agent/tools/create_purchase_draft", json=args,
                                  headers={"Authorization": f"Bearer {token}"})
    assert rest.status_code == 429


def test_journal_shows_calls_refusals_and_objects(app, admin):
    token, key_id = _key(admin)
    _get(app, token)
    _get(app, token, "/api/v1/bank-accounts")                     # domaine refusé
    _tool(app, token, "create_purchase_draft", {"supplier": {"name": "Coop"}, "issue_date": "2026-11-03", "total": 10})
    journal = admin.get(f"/api/v1/api-keys/{key_id}/calls").json
    targets = [(c["target"], c["status"]) for c in journal["items"]]
    assert ("api.purchases_list", 200) in targets and ("api.bank_accounts_list", 403) in targets
    created = [c for c in journal["items"] if c["object"]]
    assert created and created[0]["object"]["url"].startswith("/purchases/")
    assert journal["meta"]["creations_today"] == 1
    errors = admin.get(f"/api/v1/api-keys/{key_id}/calls?kind=errors").json["items"]
    assert [c["status"] for c in errors] == [403] and "Banque" in errors[0]["error"]
    assert db.session.get(ApiKey, key_id).last_used_at is not None


def test_revoked_key_journal_keeps_last_accepted_call(app, admin):
    """Récit 5 : après révocation, 401 ; le journal montre le dernier appel accepté."""
    token, key_id = _key(admin)
    assert _get(app, token).status_code == 200
    admin.post(f"/api/v1/api-keys/{key_id}/revoke")
    assert _get(app, token).status_code == 401
    items = admin.get(f"/api/v1/api-keys/{key_id}/calls").json["items"]
    assert items[0]["target"] == "api.purchases_list" and items[0]["status"] == 200


def test_purge_after_180_days(app, admin):
    from app.services import api_journal
    token, key_id = _key(admin)
    db.session.add(ApiCall(key_id=key_id, at=datetime.utcnow() - timedelta(days=200), channel="rest", target="old"))
    db.session.commit()
    api_journal.reset()
    _get(app, token)
    assert ApiCall.query.filter_by(target="old").count() == 0


def test_owner_sees_own_journal_and_help(app, admin):
    from app.models import InstanceMembership
    _token, key_id = _key(admin)                      # clé rattachée à soi, puis rôle trésorier
    db.session.query(InstanceMembership).update({"role": "treasurer"})
    db.session.commit()
    assert admin.get("/api/v1/api-keys").status_code == 403
    assert [k["id"] for k in admin.get("/api/v1/me/api-keys").json["items"]] == [key_id]
    assert admin.get(f"/api/v1/api-keys/{key_id}/calls").status_code == 200
    help_ = admin.get("/api/v1/api-keys/help").json
    names = {t["name"] for t in help_["tools"]}
    assert {"create_purchase_draft", "get_context", "list_purchases"} <= names and "get_aids" not in names
    assert {d["key"] for d in help_["domains"]} >= {"purchases", "accounting"}


def test_rate_window_slides():
    from app.services import api_journal
    api_journal.reset()
    assert api_journal.rate_check(99, 1, now=100.0) is None
    assert api_journal.rate_check(99, 1, now=130.0) == 31
    assert api_journal.rate_check(99, 1, now=161.0) is None


def test_agent_requests_are_size_limited(app, admin):
    token, _key_id = _key(admin)
    big = "A" * (16 * 1024 * 1024)
    res = app.test_client().post("/mcp", headers={"Authorization": f"Bearer {token}"}, data=big,
                                 content_type="application/json")
    assert res.status_code == 413


# ------------------------------------------------------------------ revue de sécurité AK4


def test_calculator_prefill_needs_accounting(app, admin):
    token, _ = _key(admin, read_domains=["documents"], write_domains=[])
    res = _tool(app, token, "run_calculator", {"code": "dep", "values": [], "prefill": True}).json["result"]
    assert res["isError"] is True and "Comptabilité" in res["structuredContent"]["error"]


def test_batches_are_capped_and_counted(app, admin):
    token, _ = _key(admin, rate_per_minute=3)
    ping = lambda i: {"jsonrpc": "2.0", "id": i, "method": "ping"}  # noqa: E731
    headers = {"Authorization": f"Bearer {token}"}
    too_big = app.test_client().post("/mcp", headers=headers, json=[ping(i) for i in range(11)])
    assert too_big.status_code == 400
    replies = app.test_client().post("/mcp", headers=headers, json=[ping(i) for i in range(5)]).json
    # 1 requête HTTP (débit 1) + 4 messages suivants comptés : 2 passent, les autres sont refusés.
    assert [("result" in r) for r in replies] == [True, True, False, False, False]


def test_uploads_count_against_daily_cap(app, admin):
    import io
    token, key_id = _key(admin, creations_per_day=1)
    headers = {"Authorization": f"Bearer {token}"}
    pdf = b"%PDF-1.4\n%%EOF\n"
    first = app.test_client().post("/api/v1/agent/files", headers=headers, data={"file": (io.BytesIO(pdf), "a.pdf")},
                                   content_type="multipart/form-data")
    assert first.status_code == 201, first.json
    second = app.test_client().post("/api/v1/agent/files", headers=headers, data={"file": (io.BytesIO(pdf), "b.pdf")},
                                    content_type="multipart/form-data")
    assert second.status_code == 429


def test_attach_document_only_on_own_drafts(app, admin):
    import base64
    token_a, _ = _key(admin)
    token_b, _ = _key(admin, name="Autre usage")
    out = _tool(app, token_a, "create_purchase_draft", {"supplier": {"name": "Coop"}, "issue_date": "2026-11-03",
                                                         "total": 10}).json["result"]["structuredContent"]
    pdf = base64.b64encode(b"%PDF-1.4\n%%EOF\n").decode()
    other = _tool(app, token_b, "attach_document", {"purchase_id": out["purchase_id"],
                                                    "file": {"name": "x.pdf", "content_base64": pdf}}).json["result"]
    assert other["isError"] is True and "cette clé" in other["structuredContent"]["error"]
    own = _tool(app, token_a, "attach_document", {"purchase_id": out["purchase_id"],
                                                  "file": {"name": "x.pdf", "content_base64": pdf}}).json["result"]
    assert own["isError"] is False and own["structuredContent"]["has_attachment"] is True


def test_internal_errors_stay_generic(app, admin, monkeypatch):
    from app.services import agent_tools
    token, _ = _key(admin)
    monkeypatch.setattr(agent_tools, "list_purchases", lambda args: 1 / 0)
    monkeypatch.setattr(agent_tools, "OWN_TOOLS", tuple(
        t if t.name != "list_purchases" else agent_tools.AgentTool(t.name, t.title, t.domain, t.description, t.schema,
                                                                    agent_tools.list_purchases)
        for t in agent_tools.OWN_TOOLS))
    res = _tool(app, token, "list_purchases", {}).json["result"]
    assert res["isError"] is True and "ZeroDivision" not in res["structuredContent"]["error"]


def test_accountant_key_reads_tools_by_rest(app, admin):
    from app.models import InstanceMembership
    token, _ = _key(admin, write_domains=[])
    db.session.query(InstanceMembership).update({"role": "accountant"})
    db.session.commit()
    res = app.test_client().post("/api/v1/agent/tools/list_purchases", json={}, headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.json
