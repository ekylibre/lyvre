"""Lot AG9b.a : intégration « Assistant Claude », conversation diffusée (SSE), outils, rôles, quota (AGD26).

L'API Claude n'est jamais appelée : `settings.client` est remplacé par un faux client qui rejoue des réponses."""
import json
from types import SimpleNamespace

import pytest

from app.extensions import db
from app.models import AssistantConversation, AssistantMessage
from app.services import external_config
from app.services.assistant import loop, settings
from test_agri_fixtures import _agri_instance


class Block(SimpleNamespace):
    def to_dict(self):
        return {k: v for k, v in vars(self).items()}


def _text(text):
    return Block(type="text", text=text)


def _tool(name, args, ident="tu_1"):
    return Block(type="tool_use", id=ident, name=name, input=args)


def _message(blocks, stop="end_turn"):
    return SimpleNamespace(content=blocks, stop_reason=stop, model="claude-haiku-5-5",
                           usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0,
                                                 cache_creation_input_tokens=0))


class FakeStream:
    def __init__(self, message):
        self.message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for block in self.message.content:
            if block.type == "text":
                yield SimpleNamespace(type="text", text=block.text)

    def get_final_message(self):
        return self.message


class FakeClient:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))
        self.models = SimpleNamespace(retrieve=lambda model: SimpleNamespace(display_name=model))

    def _stream(self, **params):
        self.calls.append(json.loads(json.dumps(params, default=str)))
        return FakeStream(self.replies.pop(0))


@pytest.fixture()
def farm(app, login_as, monkeypatch):
    fake = FakeClient([])
    monkeypatch.setattr(settings, "client", lambda timeout=None: fake)     # jamais d'appel réel (sonde comprise)
    client = login_as(role="admin")
    _agri_instance()
    assert client.post("/api/v1/integrations/assistant/enabled", json={"enabled": True}).status_code == 200
    assert client.put("/api/v1/integrations/assistant", json={"values": {"api_key": "sk-ant-test"}}).status_code == 200
    return {"client": client, "fake": fake, "monkeypatch": monkeypatch}


def _fresh():
    """Le cache des réglages vit dans `g` ; les tests partagent un contexte d'application."""
    from flask import g
    g.pop("_ext_config_cache", None)


def _events(resp):
    out = []
    for chunk in resp.get_data(as_text=True).split("\n\n"):
        if chunk.startswith("event:"):
            out.append(json.loads(chunk.split("data: ", 1)[1]))
    return out


def test_integration_and_status(app, login_as):
    client = login_as(role="admin")
    assert client.get("/api/v1/assistant/status").get_json()["item"]["applies"] is False     # non agricole
    _agri_instance()
    status = client.get("/api/v1/assistant/status").get_json()["item"]
    assert status["applies"] and not status["available"] and status["message"]
    detail = client.get("/api/v1/integrations/assistant").get_json()
    assert {f["key"] for f in detail["fields"]} == {"api_key", "model", "monthly_tokens", "lexicon"}
    assert client.post("/api/v1/assistant/conversations").status_code == 409


def test_server_key_locks_the_integration(app, login_as, monkeypatch):
    monkeypatch.setattr(settings, "client", lambda timeout=None: FakeClient([]))
    client = login_as(role="admin")
    _agri_instance()
    app.config["ANTHROPIC_API_KEY"] = "sk-ant-server"
    try:
        status = client.get("/api/v1/assistant/status").get_json()["item"]
        assert status["available"] and status["server_key"] and status["model"] == "claude-haiku-5-5"
        field = next(f for f in client.get("/api/v1/integrations/assistant").get_json()["fields"] if f["key"] == "api_key")
        assert field["source"] == "server" and field["value"] == ""
        assert client.post("/api/v1/integrations/assistant/enabled", json={"enabled": False}).status_code == 409
        client.put("/api/v1/integrations/assistant", json={"values": {"api_key": "sk-ant-instance", "model": "claude-opus-5-5"}})
        _fresh()
        assert external_config.get("assistant", "api_key") == "sk-ant-server"
        assert settings.model() == "claude-opus-5-5"
    finally:
        app.config["ANTHROPIC_API_KEY"] = ""


def test_conversation_with_tool(farm):
    client, fake = farm["client"], farm["fake"]
    fake.replies += [_message([_text("Je regarde."), _tool("get_agenda", {})], stop="tool_use"),
                     _message([_text("Rien d'urgent cette semaine.")])]
    conv = client.post("/api/v1/assistant/conversations").get_json()["item"]
    resp = client.post(f"/api/v1/assistant/conversations/{conv['id']}/messages",
                       json={"text": "Qu'ai-je à payer ?", "page": {"route": "/agenda/"}})
    assert resp.mimetype == "text/event-stream"
    events = _events(resp)
    assert [e["type"] for e in events] == ["text", "tool", "text", "done"]
    assert events[1]["name"] == "get_agenda" and events[-1]["usage"]["input"] == 2000
    first, second = fake.calls
    names = [t["name"] for t in first["tools"]]
    assert names == sorted(names) and {"get_agenda", "get_context"} <= set(names)
    assert all(t["strict"] for t in first["tools"]) and first["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert first["model"] == "claude-haiku-5-5" and "fallbacks" not in first and first["output_config"] == {"effort": "medium"}
    assert [m["role"] for m in first["messages"]] == ["user", "system"]
    assert "Écran ouvert : /agenda/." in first["messages"][1]["content"]
    assert [m["role"] for m in second["messages"]] == ["user", "system", "assistant", "user"]
    result = second["messages"][3]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "tu_1" and "items" in json.loads(result["content"])
    detail = client.get(f"/api/v1/assistant/conversations/{conv['id']}").get_json()["item"]
    assert detail["title"] == "Qu'ai-je à payer ?"
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "assistant"]
    assert detail["messages"][1]["tools"] == ["get_agenda"]


def test_context_tool_refusal_and_model_fallback(farm):
    client, fake = farm["client"], farm["fake"]
    client.put("/api/v1/integrations/assistant", json={"values": {"model": "claude-opus-5-5"}})
    fake.replies += [_message([_tool("get_context", {})], stop="tool_use"), _message([], stop="refusal")]
    conv = client.post("/api/v1/assistant/conversations").get_json()["item"]
    events = _events(client.post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"text": "Qui suis-je ?"}))
    assert [e["type"] for e in events] == ["tool", "error", "done"]
    assert fake.calls[0]["fallbacks"] == "default" and fake.calls[0]["betas"] == [loop.FALLBACK_BETA]
    result = json.loads(fake.calls[1]["messages"][3]["content"][0]["content"])
    assert result["structure"]["chart"] == "agri" and "fiscal_years" in result


def test_unknown_tool_quota_and_roles(farm, login_as):
    client, fake = farm["client"], farm["fake"]
    fake.replies += [_message([_tool("propose_entry", {"x": 1})], stop="tool_use"), _message([_text("ok")])]
    conv = client.post("/api/v1/assistant/conversations").get_json()["item"]
    _events(client.post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"text": "Passe l'écriture"}))
    result = fake.calls[1]["messages"][3]["content"][0]
    assert result["is_error"] is True and "non conformes" in result["content"]
    client.put("/api/v1/integrations/assistant", json={"values": {"monthly_tokens": "100"}})
    events = _events(client.post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"text": "Encore ?"}))
    assert events == [{"type": "error", "message": "Quota mensuel de l'assistant atteint (Configuration › Intégrations)."}]
    assert AssistantMessage.query.filter_by(conversation_id=conv["id"]).count() == 5
    other = AssistantConversation(user_id=999)
    db.session.add(other)
    db.session.commit()
    assert client.get(f"/api/v1/assistant/conversations/{other.id}").status_code == 404     # conversation d'autrui
    assert client.delete(f"/api/v1/assistant/conversations/{conv['id']}").status_code == 200
    # expert-comptable : converse (lecture seule), sans outil de proposition
    from app.models import InstanceMembership
    for membership in InstanceMembership.query.all():
        membership.role = "accountant"
    db.session.commit()
    status = client.get("/api/v1/assistant/status").get_json()["item"]
    assert status["can_propose"] is False
    assert client.post("/api/v1/assistant/conversations").status_code == 201
    assert db.session.get(AssistantConversation, conv["id"]) is None


def test_read_tools_and_corpus(farm):
    """Lot AG9b.b : outils de lecture sur le dossier, corpus en cache, contexte « à compléter »."""
    from datetime import date as day

    from app.models import Account, FiscalYear, Journal
    from app.services.assistant import corpus, prompt, tools
    from app.services.ledger import post_entry
    fy = FiscalYear(label="2026", start_date=day(2026, 1, 1), end_date=day(2026, 12, 31))
    od = Journal(code="OD", label="OD")
    db.session.add_all([fy, od])
    db.session.commit()
    ids = {c: Account.query.filter_by(code=c).one().id for c in ("411", "7011", "60111", "401")}
    post_entry(fy.id, od.id, day(2026, 3, 1), "Vente de blé", [
        {"account_id": ids["411"], "label": "Vente de blé", "debit_cents": 1234500, "credit_cents": 0},
        {"account_id": ids["7011"], "label": "Vente de blé", "debit_cents": 0, "credit_cents": 1234500}])

    def call(name, **args):
        content, error = tools.run(name, args, False)
        return json.loads(content), error

    balances, err = call("get_balances", prefixes="701 411", fiscal_year="2026")
    assert not err and {a["account"]: a["balance"] for a in balances["accounts"]} == {"411": "12 345,00 €", "7011": "-12 345,00 €"}
    entries, _ = call("search_entries", text="blé", fiscal_year="2026")
    assert entries["lines"][0]["label"] == "Vente de blé" and len(entries["lines"]) == 2
    assert call("get_balances", prefixes="x")[0]["error"]
    assert "error" in call("get_vat", fiscal_year="1999")[0]
    vat, _ = call("get_vat", fiscal_year="2026")
    assert vat["returns"] == []
    tax, _ = call("get_tax_result", fiscal_year="2026")
    assert tax["accounting_result"] == "12 345,00 €"
    msa_data, _ = call("get_msa", fiscal_year="2026")
    assert msa_data["revenue_year"] == 2026 and msa_data["people"][0]["social_base"]
    margins, _ = call("get_margins", fiscal_year="2026")
    assert margins["productions"] == []
    checks, _ = call("get_closing_checks", fiscal_year="2026")
    assert isinstance(checks["checks"], list)
    assert call("get_aids")[0] == {"aids": [], "more": False}
    param, _ = call("get_parameter", key="msa.pass_cents", date="2026-06-01")
    assert param["value"] == 4806000 and param["reliability"] == "A" and param["source"].startswith("https://")
    assert call("get_parameter", key="msa.nope")[0]["similar_keys"]
    fiche, _ = call("get_deadline_fiche", id="soc-03")
    assert fiche["id"] == "SOC-03" and fiche["links"]
    text = corpus.text()
    assert "[SOC-03]" in text and "[msa.pass_cents]" in text and corpus.text() is text
    assert "régime BA" in prompt.page_context("admin", {}, True)
    # le corpus est le dernier bloc du préfixe, mis en cache
    fake = farm["fake"]
    fake.replies.append(_message([_text("ok")]))
    conv = farm["client"].post("/api/v1/assistant/conversations").get_json()["item"]
    _events(farm["client"].post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"text": "Bonjour"}))
    system = fake.calls[-1]["system"]
    assert "cache_control" not in system[0] and system[1]["cache_control"] == {"type": "ephemeral"}
    assert system[1]["text"] == text and len(fake.calls[-1]["tools"]) == 18          # admin : lecture + propositions


def test_proposals(farm):
    """Lot AG9b.c : brouillons proposés (écriture, appel MSA, échéance, navigation), jamais enregistrés par l'assistant."""
    from datetime import date as day

    from app.models import AssistantProposal, FiscalYear, InstanceMembership, Journal, JournalEntry
    client, fake = farm["client"], farm["fake"]
    db.session.add_all([FiscalYear(label="2026", start_date=day(2026, 1, 1), end_date=day(2026, 12, 31)),
                        Journal(code="OD", label="OD")])
    db.session.commit()
    client.get("/api/v1/fiscal-years/1/msa")                                    # crée l'exploitant suivi
    lines = [{"account": "60111", "label": "Engrais", "debit": "1 200,50"}, {"account": "401", "credit": "1200,50"}]
    fake.replies += [
        _message([_tool("propose_entry", {"date": "2026-03-01", "journal": "OD", "label": "Engrais", "lines": lines}, "t1"),
                  _tool("propose_entry", {"date": "2026-03-01", "lines": [{"account": "60111", "debit": "10"},
                                                                          {"account": "401", "credit": "9"}]}, "t2"),
                  _tool("navigate", {"route": "/msa/", "label": "Voir la MSA"}, "t3"),
                  _tool("navigate", {"route": "https://evil.example", "label": "x"}, "t4"),
                  _tool("propose_msa_call", {"kind": "balance", "due_on": "2026-12-08", "amount": "500"}, "t5")],
                 stop="tool_use"),
        _message([_text("Voici les brouillons.")])]
    conv = client.post("/api/v1/assistant/conversations").get_json()["item"]
    events = _events(client.post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"text": "Prépare"}))
    actions = [e["action"] for e in events if e["type"] == "action"]
    assert [a["kind"] for a in actions] == ["entry", "navigate", "msa_call"]
    entry = actions[0]
    assert entry["payload"]["lines"][0]["debit_cents"] == 120050 and "1\u202f200,50 €" in entry["summary"]
    results = fake.calls[1]["messages"][3]["content"]
    assert json.loads(results[0]["content"])["shown_to_user"] is True
    assert results[1]["is_error"] and "déséquilibrée" in results[1]["content"]
    assert results[3]["is_error"] and actions[2]["payload"]["amount_cents"] == 50000
    assert JournalEntry.query.count() == 0                                       # rien n'est passé en comptabilité
    form = client.get(f"/api/v1/entries/form?proposal_id={entry['id']}").get_json()
    assert form["proposal"]["id"] == entry["id"] and form["initial"]["lines"][0]["debit_cents"] == 120050
    assert client.patch(f"/api/v1/assistant/proposals/{entry['id']}", json={"status": "accepted", "result_ref": "42"}).status_code == 200
    assert db.session.get(AssistantProposal, entry["id"]).status == "accepted"
    detail = client.get(f"/api/v1/assistant/conversations/{conv['id']}").get_json()["item"]
    assert [a["kind"] for a in detail["messages"][1]["actions"]] == ["entry", "navigate", "msa_call"]
    # échéance : identifiants de l'échéancier, contrôle de l'occurrence
    fake.replies += [_message([_tool("propose_deadline", {"deadline_id": "nope", "occurs_on": "2026-04-30", "period": "",
                                                          "action": "done"})], stop="tool_use"), _message([_text("ok")])]
    _events(client.post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"text": "Coche"}))
    assert "introuvable" in fake.calls[-1]["messages"][-1]["content"][0]["content"]
    # expert-comptable : outils de proposition absents et refusés
    for membership in InstanceMembership.query.all():
        membership.role = "accountant"
    db.session.commit()
    fake.replies += [_message([_tool("propose_entry", {"date": "2026-03-01", "lines": lines})], stop="tool_use"),
                     _message([_text("ok")])]
    _events(client.post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"text": "Encore"}))
    assert all(not t["name"].startswith(("propose", "navigate")) for t in fake.calls[-2]["tools"])
    assert "non autorisé" in fake.calls[-1]["messages"][-1]["content"][0]["content"]
    assert client.get(f"/api/v1/entries/form?proposal_id={entry['id']}").status_code == 200   # lecture permise


def test_usage_lexicon_and_concurrency(farm):
    """Lot AG9b.d : usage et coût du mois, Lexicon (MCP) en option, deux réponses simultanées au plus."""
    client, fake = farm["client"], farm["fake"]
    client.put("/api/v1/integrations/assistant", json={"values": {"lexicon": "oui"}})
    fake.replies += [_message([Block(type="mcp_tool_use", id="m1", name="get_crop_figures", server_name="lexicon", input={}),
                               _text("Rendement moyen : voir Lexicon.")])]
    conv = client.post("/api/v1/assistant/conversations").get_json()["item"]
    events = _events(client.post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"text": "Rendement du blé ?"}))
    assert {"type": "tool", "name": "lexicon:get_crop_figures"} in events
    call = fake.calls[-1]
    assert call["mcp_servers"] == [{"type": "url", "url": settings.LEXICON_MCP_URL, "name": "lexicon"}]
    assert call["tools"][-1] == {"type": "mcp_toolset", "mcp_server_name": "lexicon"} and settings.MCP_BETA in call["betas"]
    assert "Lexicon" in call["messages"][1]["content"]
    usage = client.get("/api/v1/assistant/usage").get_json()["item"]
    assert usage["used_tokens"] == 1200 and usage["models"][0]["cost_usd"] == settings.cost_usd("claude-haiku-5-5", 1000, 200)
    assert usage["quota_tokens"] == settings.DEFAULT_MONTHLY_TOKENS
    assert loop.acquire("x") and loop.acquire("x") and not loop.acquire("x")
    loop.release("x")
    loop.release("x")
    farm["monkeypatch"].setattr(settings, "MAX_ACTIVE_PER_INSTANCE", 0)
    resp = client.post(f"/api/v1/assistant/conversations/{conv['id']}/messages", json={"text": "Encore"})
    assert resp.status_code == 409 and "déjà en cours" in resp.get_json()["error"]["message"]


def test_eval_scorer_and_cases(farm):
    """Lot AG9b.d : contrôles déterministes du jeu d'évaluation, sur un faux client (aucun appel réel)."""
    from pathlib import Path

    import yaml

    from app.services.assistant import evals
    cases = yaml.safe_load((Path(__file__).resolve().parents[1] / "assistant_evals" / "cases.yaml").read_text(encoding="utf-8"))
    assert len(cases) >= 15 and len({c["id"] for c in cases}) == len(cases)
    allowed = {"tools_any", "tools_none", "contains", "not_contains", "cites", "proposals"}
    assert all(set(c["expect"]) <= allowed and c.get("role", "admin") in ("admin", "accountant") for c in cases)
    case = {"id": "x", "question": "Échéances ?", "expect": {"tools_any": ["get_agenda"], "contains": ["TVA"],
                                                             "cites": [r"\[FIS-\d\d\]"], "proposals": []}}
    farm["fake"].replies += [_message([_tool("get_agenda", {})], stop="tool_use"),
                             _message([_text("Acompte de TVA le 05/11 [FIS-03].")])]
    run = evals.run_case(case)
    assert run["tools"] == ["get_agenda"] and evals.score(case, run) == [] and run["cost_usd"] > 0
    assert AssistantConversation.query.filter(AssistantConversation.title.like("[évaluation]%")).count() == 0
    bad = evals.score(case, {"text": "Rien", "tools": ["propose_entry"], "proposals": ["entry"], "errors": []})
    assert len(bad) == 4



def test_calculator_tools(farm):
    """Lot AG12.e : l'assistant liste et exécute les calculettes (même résultat que l'écran, rien d'enregistré)."""
    from app.services import calculators
    from app.services.assistant import tools

    def call(name, **args):
        content, error = tools.run(name, args, False)
        return json.loads(content), error

    listing, err = call("list_calculators", query="micro")
    assert not err and [c["code"] for c in listing["calculators"]] == ["micro-ba"]
    assert {i["key"] for i in listing["calculators"][0]["inputs"]} >= {"year", "receipts_n"}
    values = [{"key": k, "value": v} for k, v in {"year": "2026", "receipts_n2": "61000", "receipts_n1": "68000",
                                                    "receipts_n": "72000"}.items()]
    result, err = call("run_calculator", code="micro-ba", values=values)
    screen = calculators.run(calculators.get("micro-ba"), {v["key"]: v["value"] for v in values})
    assert not err and result["headline"] == screen["headline"] and result["link"] == "/outils/micro-ba"
    assert result["params"] and result["method"]
    seeds, _ = call("run_calculator", code="calc-dose-semis",
                    values=[{"key": "grains", "value": "300"}, {"key": "tgw", "value": "45"}, {"key": "emergence", "value": "90"}])
    assert seeds["headline"][0]["value"] == "150,0 kg/ha"
    missing, err = call("run_calculator", code="micro-ba", values=[{"key": "year", "value": "2026"}])
    assert err and missing["field"] == "receipts_n2"
    assert call("run_calculator", code="inconnue")[0]["error"]
    assert call("run_calculator", code="micro-ba", prefill="oui")[1]                 # booléen attendu
    prefilled, err = call("run_calculator", code="acompte-tva", prefill=True, values=[{"key": "due", "value": "8400"}])
    assert not err and prefilled["origins"].get("year") == "année en cours" and "due" not in prefilled["origins"]
