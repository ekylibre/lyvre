"""Serveur MCP face au client de référence (SDK Python `mcp`), en HTTP streamable réel (lot AK2, décision D1).

Le SDK n'est pas une dépendance de l'application : le test est sauté s'il n'est pas installé (`pip install mcp`).
"""
import asyncio
import threading

import pytest

mcp = pytest.importorskip("mcp")

from werkzeug.serving import make_server  # noqa: E402

from app.extensions import db  # noqa: E402


@pytest.fixture()
def server(app, login_as):
    admin = login_as(role="admin")
    token = admin.post("/api/v1/api-keys", json={"name": "Aiffel", "read_domains": ["purchases"]}).json["token"]
    db.session.remove()
    srv = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{srv.server_port}/mcp", token
    finally:
        srv.shutdown()


async def _session(url, token):
    from mcp import ClientSession
    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
    async with create_mcp_http_client(headers={"Authorization": f"Bearer {token}"}) as http:
        async with streamable_http_client(url, http_client=http) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                tools = await session.list_tools()
                call = await session.call_tool("list_purchases", {"status": "unpaid"})
                refused = await session.call_tool("get_bank_accounts", {})
                return init, tools, call, refused


def test_reference_client(server):
    url, token = server
    init, tools, call, refused = asyncio.run(_session(url, token))
    assert init.server_info.name == "lyvre"
    names = {t.name for t in tools.tools}
    assert "list_purchases" in names and "get_bank_accounts" not in names
    assert call.is_error is False and call.structured_content["purchases"] == []
    assert refused.is_error is True
