"""Testes da rota de áudio do backend da revisão (``src/user_validation.py``).

Nenhum teste toca na rede ou no Gemini: a transcrição e o modelo são falsos.
A censura com o ``ffmpeg`` a sério só corre se ele estiver instalado.
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

SOLUTION = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOLUTION / "src"))

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
pytest.importorskip("fitz")

from fastapi.testclient import TestClient  # noqa: E402

import audio  # noqa: E402
import user_validation  # noqa: E402

SENTENCE = "Contacto ana.silva@exemplo.pt para marcar."
WORDS = [
    {"text": "Contacto", "start": 0.0, "end": 0.5, "type": "word"},
    {"text": "ana.silva@exemplo.pt", "start": 0.5, "end": 1.5,
     "type": "word"},
    {"text": "para", "start": 1.5, "end": 1.8, "type": "word"},
    {"text": "marcar.", "start": 1.8, "end": 2.3, "type": "word"},
]
SCRIBE_RESPONSE = {"words": WORDS}
SOUND = SOLUTION / "assets" / "censor_sounds" / "censor_1.m4a"


class FakeScribe:
    """``call_scribe`` falso: conta os pedidos e guarda o que recebeu."""

    def __init__(self, response=None, error=None):
        self.response = SCRIBE_RESPONSE if response is None else response
        self.error = error
        self.calls = 0
        self.received = []

    def __call__(self, audio_bytes):
        self.calls += 1
        self.received.append(audio_bytes)
        if self.error:
            raise self.error
        return self.response


class FakeModel:
    """Sem instruções não devolve nada; com instruções mascara ``marcar``."""

    def __init__(self):
        self.requests = []

    def __call__(self, system, content):
        self.requests.append(content)
        if "<user_instructions>" not in content:
            return "[]"
        return json.dumps([{
            "line": 1, "text": "marcar", "category": "comportamento",
            "reason": "x", "confidence": "certo"}])


@pytest.fixture()
def fake_redact(monkeypatch):
    """Substitui o ``ffmpeg`` por um ficheiro que descreve os intervalos."""
    calls = []

    def redact(original, ranges, sounds, out):
        calls.append({"original": Path(original), "ranges": list(ranges)})
        Path(out).write_bytes(("censurado:%s" % ranges).encode())

    monkeypatch.setattr(user_validation, "redact", redact)
    monkeypatch.setattr(user_validation, "ffmpeg_available", lambda: True)
    return calls


def client(scribe=None, generate=None):
    app = user_validation.create_app(generate, scribe=scribe, sounds=[SOUND])
    return TestClient(app)


def upload(api, body=b"audio-de-teste", content_type="audio/mpeg"):
    return api.post("/api/audio", content=body,
                    headers={"Content-Type": content_type})


def test_the_audio_is_off_without_a_transcription_client(fake_redact):
    api = client()
    assert api.get("/api/current").json()["audio_enabled"] is False
    response = upload(api)
    assert response.status_code == 503
    assert "ELEVENLABS_API_KEY" in response.json()["detail"]


def test_the_audio_is_off_without_ffmpeg(monkeypatch):
    monkeypatch.setattr(user_validation, "ffmpeg_available", lambda: False)
    api = client(FakeScribe())
    assert api.get("/api/current").json()["audio_enabled"] is False
    assert upload(api).status_code == 503


def test_the_text_flow_reports_no_audio(fake_redact):
    data = client(FakeScribe()).get("/api/current").json()
    assert data["kind"] == "text"
    assert data["audio_url"] is None
    assert data["audio_ranges"] == 0
    assert data["audio_enabled"] is True


def test_an_upload_transcribes_masks_and_censors(fake_redact):
    api = client(FakeScribe())
    data = upload(api).json()
    assert data["kind"] == "audio"
    assert data["has_document"] is True
    assert data["text"] == "Contacto * para marcar."
    assert data["audio_url"] == "/api/audio/current"
    assert data["audio_ranges"] == 1
    assert data["attempt"] == 1
    assert fake_redact[0]["ranges"] == [(0.5, 1.5)]


def test_the_censored_audio_is_served_without_caching(fake_redact):
    api = client(FakeScribe())
    upload(api, body=b"ORIGINAL-SENSIVEL")
    response = api.get("/api/audio/current")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mp4"
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(b"censurado:")
    assert b"ORIGINAL-SENSIVEL" not in response.content


def test_there_is_no_audio_before_an_upload(fake_redact):
    assert client(FakeScribe()).get("/api/audio/current").status_code == 404


def test_the_audio_is_transcribed_only_once(fake_redact):
    scribe = FakeScribe()
    api = client(scribe, FakeModel())
    upload(api)
    api.post("/api/reject", json={"attempt": 1, "text": "", "reason": "a"})
    api.post("/api/reject", json={"attempt": 2, "text": "", "reason": "b"})
    assert scribe.calls == 1
    assert len(fake_redact) == 3
    # a redação volta sempre ao áudio original
    assert len({str(call["original"]) for call in fake_redact}) == 1


def test_a_rejection_turns_the_feedback_into_a_new_censored_audio(
        fake_redact):
    model = FakeModel()
    api = client(FakeScribe(), model)
    upload(api)
    first = api.get("/api/audio/current").content
    data = api.post("/api/reject", json={
        "attempt": 1, "text": "", "reason": "Mascara também a ação."}).json()
    assert data["attempt"] == 2
    assert data["text"] == "Contacto * para *."
    assert data["audio_ranges"] == 2
    assert [v["attempt"] for v in data["history"]] == [1]
    assert "Mascara também a ação." in model.requests[-1]
    second = api.get("/api/audio/current").content
    assert second != first
    assert fake_redact[-1]["ranges"] == [(0.5, 1.5), (1.8, 2.3)]


def test_old_censored_files_are_deleted(fake_redact):
    api = client(FakeScribe(), FakeModel())
    upload(api)
    session = api.app.state.session
    first = session._censored
    api.post("/api/reject", json={"attempt": 1, "text": "", "reason": "a"})
    assert not first.exists()
    assert session._censored.exists()


def test_approve_works_for_audio(fake_redact):
    api = client(FakeScribe())
    upload(api)
    data = api.post("/api/approve").json()
    assert data["status"] == "approved" and data["kind"] == "audio"


def test_a_text_upload_replaces_the_audio_and_deletes_it(fake_redact):
    api = client(FakeScribe())
    upload(api)
    folder = Path(api.app.state.session._folder.name)
    assert folder.exists()
    data = api.post("/api/document", content=b"Nome: Ana\nNIF: 123456789",
                    headers={"Content-Type": "text/plain"}).json()
    assert data["kind"] == "text" and data["audio_url"] is None
    assert not folder.exists()
    assert api.get("/api/audio/current").status_code == 404


def test_a_new_audio_replaces_the_old_one(fake_redact):
    api = client(FakeScribe())
    upload(api)
    first = Path(api.app.state.session._folder.name)
    upload(api)
    assert not first.exists()
    assert api.get("/api/current").json()["attempt"] == 1


def test_closing_the_session_deletes_the_audio_files(fake_redact):
    api = client(FakeScribe())
    upload(api)
    folder = Path(api.app.state.session._folder.name)
    api.app.state.session.close()
    assert not folder.exists()


def test_the_original_is_saved_with_the_right_extension(fake_redact):
    api = client(FakeScribe())
    for content_type, suffix in (("audio/mpeg", ".mp3"),
                                 ("audio/mp4", ".m4a"),
                                 ("audio/x-wav", ".wav"),
                                 ("audio/mpeg; charset=binary", ".mp3")):
        upload(api, content_type=content_type)
        assert fake_redact[-1]["original"].suffix == suffix


def test_unsupported_empty_and_huge_uploads(fake_redact, monkeypatch):
    api = client(FakeScribe())
    assert upload(api, content_type="image/png").status_code == 415
    assert upload(api, content_type="application/pdf").status_code == 415
    assert upload(api, body=b"").status_code == 422
    monkeypatch.setattr(user_validation, "MAX_AUDIO_BYTES", 5)
    assert upload(api, body=b"123456").status_code == 413


def test_a_transcription_failure_is_a_clean_error(fake_redact):
    scribe = FakeScribe(error=audio.ScribeRequestError("segredo-xyz"))
    response = upload(client(scribe))
    assert response.status_code == 502
    assert "segredo" not in response.text
    assert "transcrever" in response.json()["detail"]


def test_audio_without_speech_is_refused(fake_redact):
    for response in ({"words": []}, {"words": [
            {"text": " ", "start": 0, "end": 1, "type": "spacing"}]}):
        api = client(FakeScribe(response))
        assert upload(api).status_code == 422
        assert api.get("/api/current").json()["has_document"] is False


def test_a_failed_upload_leaves_no_files_behind(fake_redact, monkeypatch):
    created = []
    real = user_validation.tempfile.TemporaryDirectory

    def tracking(*args, **kwargs):
        folder = real(*args, **kwargs)
        # The session's own storage folder lives until the server closes.
        if kwargs.get("prefix") == "review_audio_":
            created.append(Path(folder.name))
        return folder

    monkeypatch.setattr(user_validation.tempfile, "TemporaryDirectory",
                        tracking)
    api = client(FakeScribe(error=audio.ScribeRequestError("x")))
    upload(api)
    assert created and not any(path.exists() for path in created)


def test_an_alignment_failure_censors_nothing(fake_redact, monkeypatch):
    def broken(*args, **kwargs):
        raise audio.AlignmentError("palavras diferentes")

    monkeypatch.setattr(
        user_validation.audio_pipeline, "run_transcript", broken)
    api = client(FakeScribe())
    response = upload(api)
    assert response.status_code == 502
    assert "nada foi censurado" in response.json()["detail"]
    assert api.get("/api/audio/current").status_code == 404


def test_a_redaction_failure_is_a_clean_error(monkeypatch):
    def broken(*args, **kwargs):
        raise audio.RedactionError("ffmpeg falhou: C:/segredo/ficheiro")

    monkeypatch.setattr(user_validation, "redact", broken)
    monkeypatch.setattr(user_validation, "ffmpeg_available", lambda: True)
    response = upload(client(FakeScribe()))
    assert response.status_code == 502
    assert "segredo" not in response.text


def test_a_failed_rejection_keeps_the_current_version_and_audio(
        fake_redact, monkeypatch):
    api = client(FakeScribe(), FakeModel())
    upload(api)
    before = api.get("/api/audio/current").content

    def broken(*args, **kwargs):
        raise audio.RedactionError("x")

    monkeypatch.setattr(user_validation, "redact", broken)
    response = api.post("/api/reject", json={
        "attempt": 1, "text": "", "reason": "a"})
    assert response.status_code == 502
    data = api.get("/api/current").json()
    assert data["attempt"] == 1 and data["history"] == []
    assert api.get("/api/audio/current").content == before


def test_a_model_failure_on_audio_is_a_clean_error(fake_redact):
    def failing(system, content):
        raise user_validation.gateway.GatewayUnavailable("segredo")

    api = client(FakeScribe(), failing)
    response = upload(api)
    assert response.status_code == 502
    assert "segredo" not in response.text


def test_the_documented_audio_fields_exist():
    snapshot = user_validation.ReviewSession().snapshot()
    for name in ("kind", "audio_url", "audio_ranges", "audio_enabled"):
        assert name in snapshot


def test_run_transcript_matches_run_without_the_audio(monkeypatch, tmp_path):
    """A refatoração não muda o resultado do pipeline de áudio."""
    import audio_pipeline

    path = tmp_path / "a.mp3"
    path.write_bytes(b"x")
    scribe = FakeScribe()
    full = audio_pipeline.run(str(path), scribe)
    lines, times = audio.transcribe(str(path), scribe)
    split = audio_pipeline.run_transcript(lines, times)
    assert split["masked"] == full["masked"]
    assert split["ranges"] == full["ranges"]


@pytest.mark.skipif(not user_validation.ffmpeg_available(),
                    reason="precisa do ffmpeg e do ffprobe instalados")
def test_with_the_real_ffmpeg_the_duration_is_kept(tmp_path):
    import subprocess

    def duration(path):
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, check=True)
        return float(out.stdout.strip())

    total = duration(SOUND)
    words = [
        {"text": "Contacto", "start": 0.0, "end": total / 4,
         "type": "word"},
        {"text": "ana.silva@exemplo.pt", "start": total / 4,
         "end": total / 2, "type": "word"},
        {"text": "para.", "start": total / 2, "end": total,
         "type": "word"},
    ]
    api = client(FakeScribe({"words": words}))
    data = upload(api, body=SOUND.read_bytes(), content_type="audio/mp4")
    assert data.json()["text"] == "Contacto * para."
    out = tmp_path / "censurado.m4a"
    out.write_bytes(api.get("/api/audio/current").content)
    assert abs(duration(out) - total) < 0.1


def test_the_shutil_module_is_what_decides_ffmpeg(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert user_validation.ffmpeg_available() is False
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/" + name)
    assert user_validation.ffmpeg_available() is True
