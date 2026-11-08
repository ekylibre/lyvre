"""Serveur MCP et outils d'agent en lecture (lot AK2, claudedocs/design_api_mcp_aiffel.md § 6, § 7, récit 2)."""
from datetime import date

import pytest

from app.extensions import db


@pytest.fixture()
def token(app, login_as):
    from app.models import FiscalYear
    admin = login_as(role="admin")
    db.session.add(FiscalYear(label=str(date.today().year), start_date=date(date.today().year, 1, 1),
                              end_date=date(date.today().year, 12, 31)))
    db.session.commit()

    def _make(read=("purchases", "agenda"), write=()):
        res = admin.post("/api/v1/api-keys", json={"name": "Aiffel — questions", "read_domains": list(read),
                                                   "write_domains": list(write)})
        assert res.status_code == 201, res.json
        return res.json["token"]
    return _make


def rpc(app, token, method, params=None, msg_id=1, headers=None):
    body = {"jsonrpc": "2.0", "method": method, **({"id": msg_id} if msg_id is not None else {}),
            **({"params": params} if params is not None else {})}
    return app.test_client().post("/mcp", json=body, headers={"Authorization": f"Bearer {token}", **(headers or {})})


def test_initialize_gives_context_and_rule(app, token):
    res = rpc(app, token(), "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                           "clientInfo": {"name": "aiffel", "version": "1"}})
    assert res.status_code == 200
    result = res.json["result"]
    assert result["protocolVersion"] == "2025-06-18"
    assert result["serverInfo"]["name"] == "lyvre" and "tools" in result["capabilities"]
    assert "BROUILLON" in result["instructions"] and "Achats" in result["instructions"]
    assert "Set-Cookie" not in res.headers
    notif = rpc(app, token(), "notifications/initialized", msg_id=None)
    assert notif.status_code == 202


def test_tools_list_follows_key_domains(app, token):
    names = {t["name"] for t in rpc(app, token(), "tools/list").json["result"]["tools"]}
    assert {"get_context", "list_purchases", "get_purchase", "get_agenda", "run_calculator"} <= names
    assert not names & {"get_bank_accounts", "get_balances", "get_vat", "propose_entry", "navigate"}
    tool = next(t for t in rpc(app, token(), "tools/list").json["result"]["tools"] if t["name"] == "list_purchases")
    assert tool["annotations"]["readOnlyHint"] is True and tool["inputSchema"]["type"] == "object"


def test_tools_call_inside_and_outside_domains(app, token):
    key = token()
    res = rpc(app, key, "tools/call", {"name": "list_purchases", "arguments": {"status": "unpaid"}}).json["result"]
    assert res["isError"] is False and res["structuredContent"]["purchases"] == []
    ctx = rpc(app, key, "tools/call", {"name": "get_context", "arguments": {}}).json["result"]
    assert ctx["isError"] is False and ctx["structuredContent"]["fiscal_years"]
    refused = rpc(app, key, "tools/call", {"name": "get_bank_accounts", "arguments": {}}).json["result"]
    assert refused["isError"] is True and refused["structuredContent"]["code"] == "domain_forbidden"
    bad = rpc(app, key, "tools/call", {"name": "list_purchases", "arguments": {"status": "toutes"}}).json["result"]
    assert bad["isError"] is True and "schéma" in bad["structuredContent"]["error"]


def test_purchase_tools_read_data(app, token):
    from app.models import Purchase
    p = Purchase(source="manual", supplier_name="Coop du Val", invoice_number="F-12", issue_date=date.today(),
                 due_date=date(2000, 1, 1), total_cents=120000, currency="EUR")
    db.session.add(p)
    db.session.commit()
    key = token()
    rows = rpc(app, key, "tools/call", {"name": "list_purchases", "arguments": {"status": "overdue"}}) \
        .json["result"]["structuredContent"]
    from app.services.assistant.tools import euros
    assert rows["count"] == 1 and rows["purchases"][0]["remaining"] == euros(120000)
    assert rows["total_remaining"] == euros(120000) and rows["purchases"][0]["url"].endswith(f"/purchases/{p.id}")
    one = rpc(app, key, "tools/call", {"name": "get_purchase", "arguments": {"id": p.id}}).json["result"]
    assert one["structuredContent"]["supplier"] == "Coop du Val"
    assert "Fournisseur à rattacher." in one["structuredContent"]["reasons"]


def test_protocol_errors(app, token):
    key = token()
    assert rpc(app, key, "resources/list").json["error"]["code"] == -32601
    client = app.test_client()
    assert client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code == 401
    assert client.get("/mcp", headers={"Authorization": f"Bearer {key}"}).status_code == 405
    batch = client.post("/mcp", headers={"Authorization": f"Bearer {key}"},
                        json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "method": "notifications/x"}])
    assert batch.status_code == 200 and batch.json == [{"jsonrpc": "2.0", "id": 1, "result": {}}]
    assert rpc(app, key, "ping", headers={"Origin": "https://evil.example"}).status_code == 403
    assert rpc(app, key, "ping", headers={"MCP-Protocol-Version": "1999-01-01"}).status_code == 400


def test_rest_agent_tools(app, token, login_as):
    key = token(read=("bank",))
    client = app.test_client()
    headers = {"Authorization": f"Bearer {key}"}
    listing = client.get("/api/v1/agent/tools", headers=headers).json["items"]
    assert {"get_bank_accounts", "list_bank_transactions", "get_context"} <= {t["name"] for t in listing}
    res = client.post("/api/v1/agent/tools/get_bank_accounts", json={}, headers=headers)
    assert res.status_code == 200 and res.json["result"]["bank_accounts"] == []
    assert client.post("/api/v1/agent/tools/list_purchases", json={}, headers=headers).status_code == 403
    assert client.post("/api/v1/agent/tools/nope", json={}, headers=headers).status_code == 404
    # Session de l'interface : pas d'outils d'agent.
    assert login_as(is_admin=True).get("/api/v1/agent/tools").status_code == 403


def test_every_tool_has_a_known_domain():
    from app.services import agent_tools, api_domains
    for tool in agent_tools.registry():
        assert tool.domain == agent_tools.ALWAYS or tool.domain in api_domains.DOMAINS, tool.name
        assert tool.access == "read" or api_domains.writable(tool.domain), tool.name
