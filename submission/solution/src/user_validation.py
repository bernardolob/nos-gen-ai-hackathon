"""Backend da revisão manual (a UI em ``Lovable_UI_JunctionX/``).

O utilizador envia um documento, vê o texto anonimizado e aprova ou rejeita.
Ao rejeitar, as observações passam a instruções do utilizador e o pipeline
corre outra vez: é a prompt do utilizador em texto livre (ver DETECTION.md).

Só há **uma sessão** de cada vez, em memória: é um servidor local para uma
pessoa. Escuta em ``127.0.0.1`` e só aceita pedidos das origens da UI
(``REVIEW_UI_ORIGINS``, separadas por vírgulas). Sem
``GEMINI_GATEWAY_URL`` corre só com as regras de segurança.

Rotas:

- ``POST /api/document``: o corpo é o PDF (``application/pdf``) ou texto
  (``text/plain``, UTF-8); corre o pipeline e começa a revisão.
- ``GET /api/current``: a versão em revisão e o histórico.
- ``POST /api/reject``: guarda a versão, junta as observações às
  instruções e gera a tentativa seguinte.
- ``POST /api/approve``: aprova a versão atual.

Arranque, a partir de ``submission/solution/src``::

    python user_validation.py
"""

import os
import re
import tempfile
import atexit
import shutil
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote

import audio_pipeline
import detection
import gateway
import gemini_adapter
import pipeline
from audio import (
    AlignmentError,
    ConfigurationError,
    RedactionError,
    ScribeRequestError,
    TranscriptionError,
    redact,
    scribe_from_env,
    transcribe,
)
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from media import (
    MediaConfigurationError,
    MediaError,
    MediaProcessor,
    MediaRegion,
    RegionManifest,
    supported_media_kind,
)
from media.pipeline import suffix_for

HOST = "127.0.0.1"
PORT = 8000
MAX_DOCUMENT_BYTES = 10_000_000
MAX_AUDIO_BYTES = 25_000_000
# Tipos de áudio aceites e a extensão que o ffmpeg vai ver.
AUDIO_TYPES = {
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
}
AUDIO_URL = "/api/audio/current"
CENSORED_MEDIA_TYPE = "audio/mp4"
MAX_IMAGE_BYTES = 20_000_000
MAX_VIDEO_BYTES = 100_000_000
DEFAULT_ORIGINS = (
    "http://localhost:8080",
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
)
INSTRUCTIONS_HEADER = (
    "O revisor rejeitou a versão anterior e pediu o seguinte (os pedidos mais "
    "recentes prevalecem):"
)
MODEL_FAILED = "Não foi possível gerar a nova versão. Tente outra vez."
AUDIO_OFF = ("A censura de áudio não está disponível: falta a "
             "ELEVENLABS_API_KEY ou o ffmpeg.")
TRANSCRIBE_FAILED = "Não foi possível transcrever o áudio. Tente outra vez."
NO_SPEECH = "O áudio não tem fala reconhecível."
ALIGN_FAILED = ("Não foi possível alinhar a transcrição com o áudio; nada "
                "foi censurado. Tente outra vez.")
REDACT_FAILED = "Não foi possível censurar o áudio. Tente outra vez."


def ffmpeg_available():
    """Diz se o ``ffmpeg`` e o ``ffprobe`` estão instalados."""
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


class RejectedVersion(BaseModel):
    attempt: int
    text: str = ""
    reason: str = ""
    regions: int | None = None


class RegionTrackRequest(BaseModel):
    attempt: int
    seed_time_ms: int
    region: MediaRegion


class ReviewError(Exception):
    """Erro de uso da revisão; ``status`` é o código HTTP e ``message`` é
    seguro de mostrar (nunca inclui o documento)."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class ReviewSession:
    """A revisão em curso: documento, tentativa atual e histórico."""

    def __init__(self, generate=None, scribe=None, sounds=None,
                 media_processor=None):
        self.generate = generate
        self.scribe = scribe
        self.sounds = list(
            audio_pipeline.DEFAULT_SOUNDS if sounds is None else sounds)
        self.media_processor = media_processor
        self.lock = threading.Lock()
        self._folder = None
        self.storage = tempfile.TemporaryDirectory(
            prefix="veu-review-", ignore_cleanup_errors=True)
        self.job_number = 0
        self._reset()

    def audio_enabled(self):
        """Há transcrição configurada, ffmpeg e sons de substituição."""
        return bool(self.scribe and self.sounds and ffmpeg_available())

    def _close_audio(self):
        if self._folder is not None:
            self._folder.cleanup()
            self._folder = None
        self._original = None
        self._censored = None
        self._word_times = None

    def _reset(self):
        self._close_audio()
        self.kind = "text"
        self.lines = []
        self.status = "idle"
        self.progress = {"stage": "", "completed": 0, "total": 0}
        self.media = None
        self.model = None
        self.regions = []
        self.content_type = ""
        self.source_path = None
        self.output_path = None
        self.failure = ""
        self.attempt = 1
        self.text = ""
        self.history = []
        self.reasons = []
        self.result = None
        self.approved = False

    def close(self):
        """Apaga os ficheiros da sessão e fecha o processador multimédia."""
        with self.lock:
            self._close_audio()
        if self.media_processor is not None:
            self.media_processor.close()
        self.storage.cleanup()

    def _clear_files(self):
        root = Path(self.storage.name).resolve()
        for path in root.iterdir():
            if path.is_file():
                try:
                    path.unlink(missing_ok=True)
                except PermissionError:
                    # A superseded video worker may still be closing its
                    # decoder on Windows. Its result is discarded by job id.
                    pass

    def load(self, lines):
        """Começa uma revisão nova com o documento dado."""
        if not any(line.strip() for line in lines):
            raise ReviewError(422, "O documento não tem texto.")
        with self.lock:
            result = self._run(lines, [])
            self.job_number += 1
            self._clear_files()
            self._reset()
            self.lines = lines
            self.status = "ready"
            self._set(result)

    def load_audio(self, body, suffix):
        """Começa uma revisão nova com um áudio.

        Transcreve **uma só vez** (o áudio vai para o ElevenLabs); as
        rejeições seguintes repetem só a deteção e a censura, a partir da
        transcrição guardada.
        """
        if not self.audio_enabled():
            raise ReviewError(503, AUDIO_OFF)
        folder = tempfile.TemporaryDirectory(
            prefix="review_audio_", ignore_cleanup_errors=True)
        try:
            original = Path(folder.name) / ("original" + suffix)
            original.write_bytes(body)
            lines, times = self._transcribe(original)
            with self.lock:
                result, censored = self._run_audio(
                    original, lines, times, [], folder, 1)
                self.job_number += 1
                self._clear_files()
                self._reset()
                self.kind = "audio"
                self._folder = folder
                self._original = original
                self._censored = censored
                self._word_times = times
                self.lines = result["lines"]
                self._set(result)
        except BaseException:
            folder.cleanup()
            raise

    def censored_path(self):
        """Caminho do áudio censurado da versão atual."""
        with self.lock:
            if self._censored is None or not self._censored.exists():
                raise ReviewError(404, "Ainda não há áudio censurado.")
            return self._censored

    def load_media(self, body, content_type, filename="media"):
        """Start fail-closed media analysis in a background thread."""

        if self.media_processor is None:
            raise ReviewError(
                503, "O modelo multimodal não está configurado ou não "
                     "suporta imagem/vídeo.")
        kind = supported_media_kind(content_type)
        if kind is None:
            raise ReviewError(415, "Envie uma imagem ou vídeo suportado.")
        limit = MAX_IMAGE_BYTES if kind == "image" else MAX_VIDEO_BYTES
        if len(body) > limit:
            label = "imagem" if kind == "image" else "vídeo"
            raise ReviewError(413, "O %s é demasiado grande." % label)
        with self.lock:
            self.job_number += 1
            job = self.job_number
            self._clear_files()
            self._reset()
            self.kind = kind
            self.status = "processing"
            self.content_type = content_type.split(";", 1)[0].lower()
            safe_name = _safe_filename(filename)
            source = Path(self.storage.name) / (
                "source" + suffix_for(self.content_type))
            source.write_bytes(body)
            self.source_path = source
            self.media = {
                "source_url": "/api/media/source",
                "width": 0,
                "height": 0,
                "filename": safe_name,
            }
        thread = threading.Thread(
            target=self._analyze_media,
            args=(job, source, self.content_type, None), daemon=True)
        thread.start()

    def _analyze_media(self, job, source, content_type, instructions):
        def progress(stage, completed, total):
            with self.lock:
                if job == self.job_number:
                    self.progress = {
                        "stage": stage, "completed": completed,
                        "total": total,
                    }
        try:
            kind, info, regions, model = self.media_processor.analyze(
                source, content_type, progress, instructions)
        except (MediaError, OSError, RuntimeError) as error:
            with self.lock:
                if job == self.job_number:
                    self.status = "failed"
                    self.failure = str(error)
            return
        with self.lock:
            if job != self.job_number:
                return
            self.kind = kind
            self.media.update(info)
            self.regions = regions
            self.model = model.as_dict()
            self.status = "ready"
            self.failure = ""

    def update_regions(self, manifest):
        with self.lock:
            self._require_media_ready()
            if manifest.attempt != self.attempt:
                raise ReviewError(409, "A versão em revisão já mudou.")
            duration = (self.media or {}).get("duration_ms", 0)
            for region in manifest.regions:
                if region.end_ms < region.start_ms:
                    raise ReviewError(
                        422, "Um intervalo de ocultação é inválido.")
                if self.kind == "image" and (
                        region.start_ms != 0 or region.end_ms != 0):
                    raise ReviewError(
                        422, "Uma região de imagem deve usar 0 ms.")
                if self.kind == "video" and region.end_ms > duration:
                    raise ReviewError(
                        422, "Uma região excede a duração do vídeo.")
            self.regions = [region.model_copy(deep=True)
                            for region in manifest.regions]
            self.approved = False
            self.output_path = None
            if self.media:
                self.media.pop("output_url", None)

    def track_region(self, request):
        with self.lock:
            self._require_media_ready()
            if self.kind != "video":
                raise ReviewError(409, "Só é possível rastrear num vídeo.")
            if request.attempt != self.attempt:
                raise ReviewError(409, "A versão em revisão já mudou.")
            duration = (self.media or {}).get("duration_ms", 0)
            if not 0 <= request.seed_time_ms <= duration:
                raise ReviewError(422, "O instante de rastreio é inválido.")
            source = self.source_path
            job = self.job_number
        tracked = self.media_processor.track(
            source, request.region.model_copy(deep=True), duration,
            request.seed_time_ms)
        with self.lock:
            if (job != self.job_number or
                    request.attempt != self.attempt):
                raise ReviewError(409, "A versão em revisão já mudou.")
        return tracked

    def source_file(self):
        with self.lock:
            self._require_media()
            return self.source_path, self.content_type

    def output_file(self):
        with self.lock:
            if not self.approved or not self.output_path:
                raise ReviewError(
                    409, "O ficheiro anonimizado ainda não está pronto.")
            return self.output_path, (
                self.content_type
                if self.kind == "image" else "video/mp4")

    def reject(self, version):
        """Guarda a versão rejeitada e gera a seguinte com as observações."""
        with self.lock:
            self._require_document()
            if version.attempt != self.attempt:
                raise ReviewError(409, "A versão em revisão já mudou.")
            reasons = list(self.reasons)
            if version.reason.strip():
                reasons.append(version.reason.strip())
            censored = None
            if self.kind == "audio":
                result, censored = self._run_audio(
                    self._original, self.lines, self._word_times, reasons,
                    self._folder, self.attempt + 1)
            else:
                result = self._run(self.lines, reasons)
            self.history.append(RejectedVersion(
                attempt=self.attempt, text=self.text,
                reason=version.reason.strip()))
            self.reasons = reasons
            self.attempt += 1
            self._set(result)
            if censored is not None:
                previous, self._censored = self._censored, censored
                if previous is not None:
                    previous.unlink(missing_ok=True)

    def reanalyze_media(self, version):
        with self.lock:
            self._require_media_ready()
            if version.attempt != self.attempt:
                raise ReviewError(409, "A versão em revisão já mudou.")
            reasons = list(self.reasons)
            if version.reason.strip():
                reasons.append(version.reason.strip())
            instructions = build_instructions(reasons)
            self.history.append(RejectedVersion(
                attempt=self.attempt, reason=version.reason.strip(),
                regions=len(self.regions)))
            self.reasons = reasons
            self.attempt += 1
            self.status = "processing"
            self.approved = False
            self.job_number += 1
            job = self.job_number
            source, content_type = self.source_path, self.content_type
        thread = threading.Thread(
            target=self._analyze_media,
            args=(job, source, content_type, instructions), daemon=True)
        thread.start()

    def approve(self):
        with self.lock:
            if self.kind in ("text", "audio"):
                self._require_document()
                self.approved = True
                return
            self._require_media_ready()
            self.status = "exporting"
            self.job_number += 1
            job = self.job_number
            extension = (
                suffix_for(self.content_type)
                if self.kind == "image" else ".mp4")
            output = Path(self.storage.name) / ("anonymized" + extension)
            regions = [region.model_copy(deep=True) for region in self.regions]
            source, content_type = self.source_path, self.content_type
        thread = threading.Thread(
            target=self._render_media,
            args=(job, source, content_type, regions, output), daemon=True)
        thread.start()

    def _render_media(self, job, source, content_type, regions, output):
        def progress(stage, completed, total):
            with self.lock:
                if job == self.job_number:
                    self.progress = {
                        "stage": stage, "completed": completed,
                        "total": total,
                    }
        try:
            self.media_processor.render(
                source, content_type, regions, output, progress)
        except (MediaError, OSError, RuntimeError) as error:
            with self.lock:
                if job == self.job_number:
                    self.status = "failed"
                    self.failure = str(error)
            return
        with self.lock:
            if job != self.job_number:
                output.unlink(missing_ok=True)
                return
            self.output_path = output
            self.media["output_url"] = "/api/media/output"
            self.status = "ready"
            self.approved = True

    def snapshot(self):
        with self.lock:
            result = self.result
            snapshot = {
                "has_document": (
                    bool(self.lines) or self.source_path is not None),
                "kind": self.kind,
                "status": self.status,
                "progress": dict(self.progress),
                "audio_url": AUDIO_URL if self._censored else None,
                "audio_ranges": (
                    len(result["ranges"])
                    if self.kind == "audio" and result else 0),
                "audio_enabled": self.audio_enabled(),
                "attempt": self.attempt,
                "text": self.text,
                "approved": self.approved,
                "history": [v.model_dump() for v in self.history],
                "mode": (
                    "multimodal" if self.kind in ("image", "video")
                    else "model" if self.generate else "rules"),
                "warnings": len(result["warnings"]) if result else 0,
                "issues": len(result["issues"]) if result else 0,
            }
            snapshot.update({
                "media": dict(self.media or {}),
                "regions": [region.model_dump() for region in self.regions],
                "model": self.model,
                "error": self.failure,
            })
            return snapshot

    def _require_document(self):
        if not self.lines:
            raise ReviewError(409, "Ainda não há nenhum documento.")

    def _require_media(self):
        if self.kind not in {"image", "video"} or self.source_path is None:
            raise ReviewError(409, "Ainda não há nenhuma imagem ou vídeo.")

    def _require_media_ready(self):
        self._require_media()
        if self.status != "ready":
            raise ReviewError(
                409, "A análise multimédia ainda não terminou.")

    def _set(self, result):
        self.result = result
        self.text = "\n".join(result["masked"])

    def _run(self, lines, reasons):
        instructions = build_instructions(reasons)
        try:
            return pipeline.run(lines, self.generate, instructions)
        except (detection.DetectionError, gateway.GatewayError):
            raise ReviewError(502, MODEL_FAILED) from None

    def _transcribe(self, path):
        try:
            lines, times = transcribe(path, self.scribe)
        except ScribeRequestError:
            raise ReviewError(502, TRANSCRIBE_FAILED) from None
        except TranscriptionError:
            raise ReviewError(422, NO_SPEECH) from None
        if not any(line.strip() for line in lines):
            raise ReviewError(422, NO_SPEECH)
        return lines, times

    def _run_audio(self, original, lines, times, reasons, folder, number):
        """Deteta e censura. Devolve ``(resultado, áudio_censurado)``."""
        instructions = build_instructions(reasons)
        try:
            result = audio_pipeline.run_transcript(
                lines, times, self.generate, instructions)
        except (detection.DetectionError, gateway.GatewayError):
            raise ReviewError(502, MODEL_FAILED) from None
        except AlignmentError:
            raise ReviewError(502, ALIGN_FAILED) from None
        out = Path(folder.name) / ("censored_%d.m4a" % number)
        try:
            redact(original, result["ranges"], self.sounds, out)
        except (RedactionError, OSError):
            raise ReviewError(502, REDACT_FAILED) from None
        return result, out


def build_instructions(reasons):
    """Junta as observações do revisor num texto para o modelo.

    Cabem no máximo ``pipeline.MAX_INSTRUCTIONS`` caracteres: se não couberem
    todas, ficam as mais recentes. Devolve ``None`` sem observações.
    """
    kept = []
    size = len(INSTRUCTIONS_HEADER)
    for reason in reversed(reasons):
        size += len(reason) + 3
        if size > pipeline.MAX_INSTRUCTIONS:
            if not kept:
                raise ReviewError(
                    422, "As observações são demasiado compridas "
                    "(máximo %d caracteres)." % pipeline.MAX_INSTRUCTIONS)
            break
        kept.append(reason)
    if not kept:
        return None
    return "\n- ".join([INSTRUCTIONS_HEADER] + list(reversed(kept)))


def lines_from_upload(content_type, body):
    """Linhas do documento enviado (PDF ou texto UTF-8)."""
    if len(body) > MAX_DOCUMENT_BYTES:
        raise ReviewError(413, "O documento é demasiado grande.")
    kind = content_type.split(";")[0].strip().lower()
    if kind == "application/pdf":
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            path = Path(folder) / "documento.pdf"
            path.write_bytes(body)
            try:
                return pipeline.read_lines(path)
            except (RuntimeError, OSError):
                raise ReviewError(
                    422, "Não foi possível ler o PDF.") from None
    if kind == "text/plain":
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            raise ReviewError(
                422, "O texto tem de estar em UTF-8.") from None
        import pdf_extractor
        text = pdf_extractor.remove_empty_lines(text)
        return detection.normalize_lines(text.split("\n")) if text else []
    raise ReviewError(415, "Envie um PDF ou texto simples (UTF-8).")


def audio_suffix(content_type, body):
    """Extensão do áudio enviado, validando o tipo e o tamanho."""
    if len(body) > MAX_AUDIO_BYTES:
        raise ReviewError(413, "O áudio é demasiado grande.")
    kind = content_type.split(";")[0].strip().lower()
    if kind not in AUDIO_TYPES:
        raise ReviewError(415, "Envie áudio mp3, m4a ou wav.")
    if not body:
        raise ReviewError(422, "O áudio está vazio.")
    return AUDIO_TYPES[kind]


def _safe_filename(value):
    name = Path(unquote(value or "media")).name
    name = re.sub(r"[^\w. -]", "_", name, flags=re.UNICODE).strip(" .")
    return name[:120] or "media"


def allowed_origins(environ=None):
    env = os.environ if environ is None else environ
    value = env.get("REVIEW_UI_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in value.split(",") if o.strip()]
    if "*" in origins:
        raise ValueError("REVIEW_UI_ORIGINS não pode conter *.")
    return origins or list(DEFAULT_ORIGINS)


def create_app(generate=None, origins=None, scribe=None, sounds=None,
               media_processor=None):
    """Cria a aplicação.

    ``generate`` é o modelo (None = só as regras); ``scribe`` é a
    transcrição de áudio (None = a rota de áudio fica desligada);
    ``sounds`` são os sons de substituição (por defeito, os de
    ``assets/censor_sounds/``); ``media_processor`` trata imagem e vídeo
    (None = essas rotas ficam desligadas).
    """
    session = ReviewSession(generate, scribe, sounds, media_processor)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            session.close()

    app = FastAPI(title="Revisão de anonimização", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or allowed_origins(),
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Content-Type", "X-File-Name"],
    )
    app.state.session = session
    atexit.register(session.close)

    @app.exception_handler(ReviewError)
    async def review_error(_request, error):
        return JSONResponse(
            {"detail": error.message}, status_code=error.status)

    @app.post("/api/document")
    async def upload(request: Request):
        body = await request.body()
        content_type = request.headers.get("content-type", "")
        if supported_media_kind(content_type):
            session.load_media(
                body, content_type,
                request.headers.get("x-file-name", "media"))
            return session.snapshot()
        lines = lines_from_upload(content_type, body)
        await run_in_threadpool(session.load, lines)
        return session.snapshot()

    @app.post("/api/audio")
    async def upload_audio(request: Request):
        body = await request.body()
        suffix = audio_suffix(request.headers.get("content-type", ""), body)
        await run_in_threadpool(session.load_audio, body, suffix)
        return session.snapshot()

    @app.get("/api/audio/current")
    def current_audio():
        return FileResponse(
            session.censored_path(), media_type=CENSORED_MEDIA_TYPE,
            headers={"Cache-Control": "no-store"})

    @app.get("/api/current")
    def current():
        return session.snapshot()

    @app.get("/api/ready")
    def ready():
        if session.media_processor is None:
            return {"status": "ready", "media_ready": False, "model": None}
        try:
            model = session.media_processor.verify_model()
        except MediaError:
            return JSONResponse({
                "status": "degraded", "media_ready": False,
                "model": None,
            }, status_code=503)
        return {
            "status": "ready", "media_ready": True,
            "model": model.as_dict(),
        }

    @app.post("/api/reject")
    def reject(version: RejectedVersion):
        if session.kind in ("text", "audio"):
            session.reject(version)
        else:
            session.reanalyze_media(version)
        return session.snapshot()

    @app.post("/api/approve")
    def approve():
        session.approve()
        data = session.snapshot()
        if data["kind"] in ("text", "audio"):
            data["status"] = "approved"
        return data

    @app.put("/api/media/regions")
    def update_regions(manifest: RegionManifest):
        session.update_regions(manifest)
        return session.snapshot()

    @app.post("/api/media/track")
    async def track_region(request: RegionTrackRequest):
        region = await run_in_threadpool(session.track_region, request)
        return region.model_dump()

    @app.get("/api/media/source")
    def media_source():
        path, content_type = session.source_file()
        return FileResponse(
            path, media_type=content_type,
            headers={"Cache-Control": "no-store"})

    @app.get("/api/media/output")
    def media_output():
        path, content_type = session.output_file()
        filename = (
            "imagem_anonimizada" + path.suffix
            if session.kind == "image" else "video_anonimizado.mp4")
        return FileResponse(
            path, media_type=content_type, filename=filename,
            headers={"Cache-Control": "no-store"})

    return app


def main():
    import uvicorn
    try:
        scribe = scribe_from_env()
    except ConfigurationError:
        scribe = None
    try:
        media_processor = MediaProcessor.from_env()
        media_processor.verify_model()
    except (MediaConfigurationError, MediaError):
        media_processor = None
    generate = (
        gemini_adapter.make_cached_generate() or gateway.from_env()
    )
    app = create_app(generate, scribe=scribe, media_processor=media_processor)
    session = app.state.session
    text_mode = (
        "Gemini (cache ativo)" if getattr(generate, "client", None)
        else "Gemini" if generate else "regras de segurança")
    print("Revisão em http://%s:%d (texto: %s; áudio: %s; multimédia: %s)" % (
        HOST, PORT, text_mode,
        "ligado" if session.audio_enabled() else "desligado",
        "Gemini" if media_processor else "indisponível"))
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
