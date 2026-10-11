"""Testes do backend da revisão manual (``src/user_validation.py``)."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("fitz")

from fastapi.testclient import TestClient  # noqa: E402

import gateway  # noqa: E402
import user_validation  # noqa: E402

DOCUMENT = "Nome: Ana Silva\nNIF: 123456789\nCidade: Porto\n"
RAW_PDF = Path(__file__).resolve().parents[3] / "raw_data" / (
    "document_to_anonymize.pdf")


def item(line, text):
    return {"line": line, "text": text, "category": "identificacao",
            "reason": "x", "confidence": "certo"}


class FakeModel:
    """Um ``generate`` que devolve itens e guarda o que recebeu."""

    def __init__(self, *items):
        self.items = list(items)
        self.requests = []

    def __call__(self, system, content):
        self.requests.append(content)
        return json.dumps(self.items)


def client(generate=None):
    return TestClient(user_validation.create_app(generate))


def upload(api, text=DOCUMENT):
    return api.post("/api/document", content=text.encode("utf-8"),
                    headers={"Content-Type": "text/plain"})


def test_before_a_document_there_is_nothing_to_review():
    data = client().get("/api/current").json()
    assert data["has_document"] is False
    assert data["text"] == ""
    assert data["history"] == []


def test_a_text_upload_runs_the_pipeline_with_the_rules():
    api = client()
    data = upload(api).json()
    assert data["text"] == "Nome: Ana Silva\nNIF: *\nCidade: Porto"
    assert data["attempt"] == 1
    assert data["mode"] == "rules"
    assert data["warnings"] == 0 and data["issues"] == 0
    assert api.get("/api/current").json() == data


def test_a_text_upload_with_a_model():
    model = FakeModel(item(1, "Ana Silva"))
    data = upload(client(model)).json()
    assert data["text"].split("\n")[0] == "Nome: * *"
    assert data["mode"] == "model"
    assert "<user_instructions>" not in model.requests[0]


@pytest.mark.skipif(not RAW_PDF.exists(), reason="sem o PDF do desafio")
def test_a_pdf_upload():
    api = client()
    response = api.post("/api/document", content=RAW_PDF.read_bytes(),
                        headers={"Content-Type": "application/pdf"})
    assert response.status_code == 200
    import time
    deadline = time.monotonic() + 5
    data = response.json()
    while data["status"] == "processing" and time.monotonic() < deadline:
        time.sleep(0.01)
        data = api.get("/api/current").json()
    assert data["kind"] == "document"
    assert data["status"] == "ready"
    assert len(data["text"].split("\n")) == 60


def test_a_corrupt_pdf_is_a_clean_error():
    response = client().post(
        "/api/document", content=b"nao e um pdf",
        headers={"Content-Type": "application/pdf"})
    assert response.status_code == 422
    assert "PDF" in response.json()["detail"]


def test_unsupported_and_invalid_uploads():
    api = client()
    wrong = api.post("/api/document", content=b"x",
                     headers={"Content-Type": "application/octet-stream"})
    assert wrong.status_code == 415
    latin = api.post("/api/document", content="Ação".encode("latin-1"),
                     headers={"Content-Type": "text/plain"})
    assert latin.status_code == 422
    assert upload(api, "  \n\n ").status_code == 422


def test_a_document_over_the_limit_is_refused(monkeypatch):
    monkeypatch.setattr(user_validation, "MAX_DOCUMENT_BYTES", 10)
    assert upload(client(), "x" * 11).status_code == 413


def test_reject_turns_the_observations_into_instructions():
    model = FakeModel(item(3, "Porto"))
    api = client(model)
    upload(api)
    response = api.post("/api/reject", json={
        "attempt": 1, "text": "x", "reason": "Mascara também a cidade."})
    data = response.json()
    assert response.status_code == 200
    assert data["attempt"] == 2
    assert [v["attempt"] for v in data["history"]] == [1]
    assert data["history"][0]["reason"] == "Mascara também a cidade."
    assert data["text"].split("\n")[2] == "Cidade: *"
    assert "Mascara também a cidade." in model.requests[-1]
    assert "<user_instructions>" in model.requests[-1]


def test_the_rejected_version_is_kept_as_it_was():
    api = client()
    upload(api)
    data = api.post("/api/reject", json={
        "attempt": 1, "text": "ignorado", "reason": "a"}).json()
    assert data["history"][0]["text"] == (
        "Nome: Ana Silva\nNIF: *\nCidade: Porto")


def test_observations_accumulate_over_attempts():
    model = FakeModel()
    api = client(model)
    upload(api)
    api.post("/api/reject", json={"attempt": 1, "text": "", "reason": "A1"})
    api.post("/api/reject", json={"attempt": 2, "text": "", "reason": "B2"})
    last = model.requests[-1]
    assert "A1" in last and "B2" in last
    assert api.get("/api/current").json()["attempt"] == 3


def test_a_rejection_without_observations_has_no_instructions():
    model = FakeModel()
    api = client(model)
    upload(api)
    api.post("/api/reject", json={"attempt": 1, "text": "", "reason": ""})
    assert "<user_instructions>" not in model.requests[-1]


def test_a_stale_attempt_is_a_conflict_and_changes_nothing():
    api = client()
    upload(api)
    response = api.post(
        "/api/reject", json={"attempt": 5, "text": "", "reason": "x"})
    assert response.status_code == 409
    assert api.get("/api/current").json()["attempt"] == 1


def test_reject_and_approve_need_a_document():
    api = client()
    reject = api.post("/api/reject", json={"attempt": 1, "text": ""})
    assert reject.status_code == 409
    assert api.post("/api/approve").status_code == 409


def test_a_model_failure_keeps_the_current_version():
    def broken(system, content):
        raise gateway.GatewayUnavailable("segredo-xyz")

    api = client()
    upload(api)
    api.app.state.session.generate = broken
    response = api.post("/api/reject", json={
        "attempt": 1, "text": "", "reason": "Mascara X."})
    assert response.status_code == 502
    assert "segredo" not in response.text
    data = api.get("/api/current").json()
    assert data["attempt"] == 1
    assert data["history"] == []
    # a observação que falhou não fica guardada para a tentativa seguinte
    assert api.app.state.session.reasons == []


def test_a_too_long_observation_is_refused():
    api = client()
    upload(api)
    response = api.post("/api/reject", json={
        "attempt": 1, "text": "", "reason": "x" * 3000})
    assert response.status_code == 422
    assert api.get("/api/current").json()["attempt"] == 1


def test_old_observations_are_dropped_to_fit_the_limit():
    reasons = ["a" * 900, "b" * 900, "c" * 900]
    text = user_validation.build_instructions(reasons)
    assert len(text) <= user_validation.pipeline.MAX_INSTRUCTIONS
    assert "c" * 900 in text and "b" * 900 in text
    assert "a" * 900 not in text
    assert user_validation.build_instructions([]) is None


def test_approve():
    api = client()
    upload(api)
    data = api.post("/api/approve").json()
    assert data["status"] == "approved" and data["approved"] is True
    assert data["text"].endswith("Cidade: Porto")


def test_a_new_document_starts_a_new_review():
    api = client()
    upload(api)
    api.post("/api/reject", json={"attempt": 1, "text": "", "reason": "a"})
    data = upload(api, "Outro: texto").json()
    assert data["attempt"] == 1 and data["history"] == []
    assert data["approved"] is False


def test_cors_only_allows_the_ui_origins():
    api = client()
    ok = api.options("/api/current", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == (
        "http://localhost:5173")
    other = api.options("/api/current", headers={
        "Origin": "http://evil.example",
        "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in other.headers


def test_origins_from_the_environment():
    assert user_validation.allowed_origins(
        {"REVIEW_UI_ORIGINS": "http://a.pt/, http://b.pt"}) == [
        "http://a.pt", "http://b.pt"]
    assert user_validation.allowed_origins({}) == list(
        user_validation.DEFAULT_ORIGINS)
    with pytest.raises(ValueError):
        user_validation.allowed_origins({"REVIEW_UI_ORIGINS": "*"})


def test_the_server_listens_only_on_localhost():
    assert user_validation.HOST == "127.0.0.1"
