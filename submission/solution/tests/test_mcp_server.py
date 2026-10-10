"""Testes do servidor MCP (``src/mcp_server.py``)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

pytest.importorskip("mcp")
pytest.importorskip("fastapi")
pytest.importorskip("fitz")

from starlette.testclient import TestClient  # noqa: E402

import mcp_server  # noqa: E402

TOKEN = "segredo-de-teste"
HEADERS = {
    "Authorization": "Bearer " + TOKEN,
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


@pytest.fixture()
def client():
    app = mcp_server.build_app(TOKEN)
    with TestClient(app, base_url="http://127.0.0.1:8765") as api:
        yield api


def rpc(api, method, params=None, headers=None, call_id=1):
    return api.post("/mcp", headers=headers or HEADERS, json={
        "jsonrpc": "2.0", "id": call_id, "method": method,
        "params": params or {}})


def call(api, name, arguments=None):
    response = rpc(api, "tools/call",
                   {"name": name, "arguments": arguments or {}})
    assert response.status_code == 200
    result = response.json()["result"]
    assert not result.get("isError")
    return result.get("structuredContent") or json.loads(
        result["content"][0]["text"])


def test_requests_without_the_token_are_refused(client):
    assert client.post("/mcp", json={}).status_code == 401
    wrong = {"Authorization": "Bearer outro"}
    assert client.post("/mcp", headers=wrong, json={}).status_code == 401
    scheme = {"Authorization": "Basic " + TOKEN}
    assert client.post("/mcp", headers=scheme, json={}).status_code == 401


def test_the_refusal_says_nothing_about_the_token(client):
    response = client.post("/mcp", json={})
    assert TOKEN not in response.text
    assert response.headers["www-authenticate"] == "Bearer"


def test_a_foreign_host_header_is_refused(client):
    headers = dict(HEADERS, Host="evil.example")
    assert rpc(client, "tools/list", headers=headers).status_code == 421


def test_extra_hosts_come_from_the_environment():
    assert mcp_server.allowed_hosts({}) == ["127.0.0.1:*", "localhost:*"]
    assert "abc.trycloudflare.com" in mcp_server.allowed_hosts(
        {"MCP_ALLOWED_HOSTS": "abc.trycloudflare.com"})
    with pytest.raises(ValueError):
        mcp_server.allowed_hosts({"MCP_ALLOWED_HOSTS": "*"})


def test_the_three_read_only_tools_are_listed(client):
    names = [t["name"] for t in rpc(client, "tools/list").json()[
        "result"]["tools"]]
    assert sorted(names) == [
        "describe_backend", "frontend_brief", "sample_response"]


def test_describe_backend_lists_every_route_of_the_real_api(client):
    data = call(client, "describe_backend")
    routes = {(e["method"], e["path"]) for e in data["endpoints"]}
    assert routes == {("POST", "/api/document"), ("GET", "/api/current"),
                      ("POST", "/api/reject"), ("POST", "/api/approve")}
    # as rotas documentadas existem mesmo no backend
    assert set(data["openapi_paths"]) == {p for _, p in routes}
    assert data["base_url"] == "http://127.0.0.1:8000"
    assert "mode" in data["snapshot_fields"]


def test_the_documented_snapshot_fields_match_the_backend():
    real = mcp_server.user_validation.ReviewSession().snapshot()
    assert set(real) == set(mcp_server.SNAPSHOT_FIELDS)


def test_every_step_has_a_sample(client):
    for step in mcp_server.STEPS:
        data = call(client, "sample_response", {"step": step})
        assert data["step"] == step
        assert data["example"]


def test_the_samples_tell_the_story_of_a_review(client):
    uploaded = call(client, "sample_response", {"step": "uploaded"})["example"]
    rejected = call(client, "sample_response", {"step": "rejected"})["example"]
    approved = call(client, "sample_response", {"step": "approved"})["example"]
    empty = call(client, "sample_response", {"step": "empty"})["example"]
    assert empty["has_document"] is False
    assert uploaded["attempt"] == 1 and uploaded["history"] == []
    assert "diabetes" not in uploaded["text"]
    assert rejected["attempt"] == 2
    assert rejected["history"][0]["reason"] == mcp_server.SAMPLE_REASON
    assert "diabetes tipo 2" in rejected["text"]
    assert approved["approved"] is True and approved["status"] == "approved"


def test_the_samples_use_only_fictional_data(client):
    text = json.dumps([call(client, "sample_response", {"step": s})
                       for s in mcp_server.STEPS], ensure_ascii=False)
    assert "ana.silva@exemplo.pt" not in text.replace(
        "Email: *", "")  # o email está mascarado nos exemplos
    assert "123456789" not in text


def test_an_unknown_step_gets_a_helpful_answer(client):
    data = call(client, "sample_response", {"step": "nao-existe"})
    assert data["error"] and "uploaded" in data["steps"]


def test_the_frontend_brief_points_at_the_ui_files(client):
    result = rpc(client, "tools/call", {"name": "frontend_brief"}).json()
    text = json.dumps(result)
    assert "review-workspace.tsx" in text
    assert "VITE_API_URL" in text


def test_no_gemini_and_no_documents_are_used(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("o servidor MCP não deve chamar o Gemini")

    monkeypatch.setattr(mcp_server.user_validation.gateway, "from_env",
                        forbidden)
    assert mcp_server.sample_responses()["uploaded"]["mode"] == "model"
