"""A rota do PDF anonimizado do backend da revisão."""

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
fitz = pytest.importorskip("fitz")

from fastapi.testclient import TestClient  # noqa: E402

import pdf_output  # noqa: E402
import user_validation  # noqa: E402

LINES = ["Relatório de Admissão", "Nome: Ana Silva", "NIF: 123456789",
         "Cidade: Porto"]


def make_pdf():
    doc = fitz.open()
    page = doc.new_page()
    for number, line in enumerate(LINES):
        page.insert_text((72, 100 + 24 * number), line, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def words(data):
    with fitz.open(stream=io.BytesIO(data), filetype="pdf") as doc:
        return [w[4] for page in doc for w in page.get_text("words")]


class FakeModel:
    def __init__(self, *texts):
        self.texts = texts

    def __call__(self, system, content):
        items = []
        for text in self.texts:
            for number, line in enumerate(LINES, start=1):
                if text in line:
                    items.append({
                        "line": number, "text": text,
                        "category": "identificacao", "reason": "x",
                        "confidence": "certo"})
        return json.dumps(items)


def client(generate=None):
    return TestClient(user_validation.create_app(generate))


def upload_pdf(api):
    return api.post("/api/document", content=make_pdf(),
                    headers={"Content-Type": "application/pdf"})


def test_a_pdf_upload_offers_the_anonymized_pdf():
    api = client(FakeModel("Ana Silva"))
    data = upload_pdf(api).json()
    assert data["pdf_url"] == "/api/pdf/current"
    reply = api.get("/api/pdf/current")
    assert reply.status_code == 200
    assert reply.headers["content-type"] == "application/pdf"
    assert reply.headers["cache-control"] == "no-store"
    found = words(reply.content)
    assert "Ana" not in found and "Silva" not in found
    assert "123456789" not in found  # the safety rules hide the tax number
    assert "Relatório" in found and "Porto" in found


def test_text_and_documents_without_a_pdf_have_no_pdf():
    api = client()
    data = api.post("/api/document", content=b"Nome: Ana Silva\n",
                    headers={"Content-Type": "text/plain"}).json()
    assert data["pdf_url"] is None
    reply = api.get("/api/pdf/current")
    assert reply.status_code == 404
    assert reply.json()["detail"] == user_validation.NO_PDF


def test_there_is_no_pdf_before_any_document():
    assert client().get("/api/pdf/current").status_code == 404


def test_a_rejection_gives_a_pdf_for_the_new_version():
    class AskedToHideTheCity:
        """Esconde a cidade só depois de o revisor o pedir."""

        def __call__(self, system, content):
            asked = "<user_instructions>" in content
            return FakeModel("Porto" if asked else "Ana Silva")(
                system, content)

    api = client(AskedToHideTheCity())
    first = upload_pdf(api).json()
    assert "Porto" in words(api.get("/api/pdf/current").content)
    api.post("/api/reject", json={
        "attempt": first["attempt"], "text": "",
        "reason": "esconde a cidade"})
    assert "Porto" not in words(api.get("/api/pdf/current").content)


def test_a_new_text_document_drops_the_old_pdf():
    api = client()
    upload_pdf(api)
    assert api.get("/api/pdf/current").status_code == 200
    api.post("/api/document", content=b"Nome: Ana Silva\n",
             headers={"Content-Type": "text/plain"})
    assert api.get("/api/pdf/current").status_code == 404


def test_a_pdf_that_cannot_be_verified_is_not_returned(monkeypatch):
    api = client()
    upload_pdf(api)

    def broken(*args, **kwargs):
        raise pdf_output.PdfOutputError("detalhe interno")

    monkeypatch.setattr(pdf_output, "anonymize_pdf", broken)
    reply = api.get("/api/pdf/current")
    assert reply.status_code == 502
    assert reply.json()["detail"] == user_validation.PDF_FAILED
    assert "detalhe interno" not in reply.text
