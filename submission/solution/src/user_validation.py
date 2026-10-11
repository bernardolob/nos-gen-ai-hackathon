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
import json
import shutil
import subprocess
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import unquote

import audio_pipeline
import detection
import gateway
import gemini_adapter
import pdf_output
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
from fastapi.responses import FileResponse, JSONResponse, Response
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
PDF_URL = "/api/pdf/current"
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
# A instrução inicial fica sempre no pedido; o resto das 2000 letras é para
# as observações das rejeições.
MAX_INITIAL_INSTRUCTIONS = 1500
INITIAL_TOO_LONG = (
    "The initial instructions are too long (maximum %d characters)."
    % MAX_INITIAL_INSTRUCTIONS)
MODEL_FAILED = "The new version could not be generated. Try again."
AUDIO_OFF = ("Audio censoring is not available: the transcription service "
             "(the gateway or ELEVENLABS_API_KEY) or ffmpeg is missing.")
TRANSCRIBE_FAILED = "The audio could not be transcribed. Try again."
NO_SPEECH = "The audio has no recognizable speech."
ALIGN_FAILED = ("The transcript could not be aligned with the audio; "
                "nothing was censored. Try again.")
REDACT_FAILED = "The audio could not be censored. Try again."
PDF_FAILED = "The anonymized PDF could not be generated. Try again."
PREVIEW_FAILED = "The preview could not be generated."
NO_PDF = "This review does not come from a PDF."


def ffmpeg_available():
    """Diz se o ``ffmpeg`` e o ``ffprobe`` estão instalados."""
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


class RejectedVersion(BaseModel):
    attempt: int
    text: str = ""
    reason: str = ""
    regions: int | None = None


class PreviewRequest(BaseModel):
    attempt: int
    time_ms: int = 0
    regions: list[MediaRegion]


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
        self.source_pdf = None
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
        self.initial = None
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

    def load(self, lines, initial=None, pdf=None):
        """Começa uma revisão nova com o documento dado.

        ``initial`` são as instruções que o utilizador escreveu ao enviar o
        ficheiro; valem na primeira versão e em todas as seguintes.
        ``pdf`` são os bytes do PDF de onde vêm as linhas, para se poder
        devolver o PDF anonimizado (ver ``pdf_path``).
        """
        if not any(line.strip() for line in lines):
            raise ReviewError(422, "The document has no text.")
        with self.lock:
            result = self._run(lines, [], initial)
            self.job_number += 1
            self._clear_files()
            self._reset()
            self.initial = initial
            self.lines = lines
            if pdf is not None:
                source = Path(self.storage.name) / "source.pdf"
                source.write_bytes(pdf)
                self.source_pdf = source
            self.status = "ready"
            self._set(result)

    def pdf_path(self):
        """Gera o PDF anonimizado da versão atual e devolve o caminho.

        É o PDF original com as palavras mascaradas apagadas e um ``*`` no
        lugar (ver ``pdf_output.py``). Nunca devolve um PDF que a verificação
        não confirme.
        """
        with self.lock:
            if self.source_pdf is None or self.result is None:
                raise ReviewError(404, NO_PDF)
            out = Path(self.storage.name) / (
                "anonymized_%d.pdf" % self.attempt)
            try:
                pdf_output.anonymize_pdf(
                    self.source_pdf, self.lines, self.result["masked"], out)
            except pdf_output.PdfOutputError:
                raise ReviewError(502, PDF_FAILED) from None
            return out

    def load_audio(self, body, suffix, initial=None):
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
                    original, lines, times, [], folder, 1, initial)
                self.job_number += 1
                self._clear_files()
                self._reset()
                self.initial = initial
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
                raise ReviewError(404, "There is no censored audio yet.")
            return self._censored

    def load_media(self, body, content_type, filename="media", initial=None):
        """Start fail-closed media analysis in a background thread."""

        if self.media_processor is None:
            raise ReviewError(
                503, "The multimodal model is not configured or does not "
                     "support images and video.")
        kind = supported_media_kind(content_type)
        if kind is None:
            raise ReviewError(415, "Send a supported image or video.")
        limit = MAX_IMAGE_BYTES if kind == "image" else MAX_VIDEO_BYTES
        if len(body) > limit:
            label = "image" if kind == "image" else "video"
            raise ReviewError(413, "The %s is too large." % label)
        with self.lock:
            self.job_number += 1
            job = self.job_number
            self._clear_files()
            self._reset()
            self.initial = initial
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
            args=(job, source, self.content_type,
                  build_instructions([], initial)), daemon=True)
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
                raise ReviewError(409, "The version under review has "
                                       "already changed.")
            duration = (self.media or {}).get("duration_ms", 0)
            for region in manifest.regions:
                if region.end_ms < region.start_ms:
                    raise ReviewError(
                        422, "A hiding interval is not valid.")
                if self.kind == "image" and (
                        region.start_ms != 0 or region.end_ms != 0):
                    raise ReviewError(
                        422, "An image region must use 0 ms.")
                if self.kind == "video" and region.end_ms > duration:
                    raise ReviewError(
                        422, "A region goes past the end of the video.")
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
                raise ReviewError(409, "Only a video can be tracked.")
            if request.attempt != self.attempt:
                raise ReviewError(409, "The version under review has "
                                       "already changed.")
            duration = (self.media or {}).get("duration_ms", 0)
            if not 0 <= request.seed_time_ms <= duration:
                raise ReviewError(422, "The tracking time is not valid.")
            source = self.source_path
            job = self.job_number
        tracked = self.media_processor.track(
            source, request.region.model_copy(deep=True), duration,
            request.seed_time_ms)
        with self.lock:
            if (job != self.job_number or
                    request.attempt != self.attempt):
                raise ReviewError(409, "The version under review has "
                                       "already changed.")
        return tracked

    def preview_media(self, request):
        """A redacted picture of the file under review, for the given regions
        (the reviewer's draft, saved or not) and, for a video, the instant."""
        with self.lock:
            self._require_media_ready()
            if request.attempt != self.attempt:
                raise ReviewError(409, "The version under review has "
                                       "already changed.")
            duration = (self.media or {}).get("duration_ms", 0)
            if self.kind == "video" and not 0 <= request.time_ms <= duration:
                raise ReviewError(422, "The requested time is not valid.")
            source, content_type = self.source_path, self.content_type
            regions = [region.model_copy(deep=True)
                       for region in request.regions]
            job = self.job_number
        try:
            data = self.media_processor.preview(
                source, content_type, regions, request.time_ms)
        except MediaError:
            raise ReviewError(502, PREVIEW_FAILED) from None
        with self.lock:
            if job != self.job_number or request.attempt != self.attempt:
                raise ReviewError(409, "The version under review has "
                                       "already changed.")
        return data

    def source_file(self):
        with self.lock:
            self._require_media()
            return self.source_path, self.content_type

    def output_file(self):
        with self.lock:
            if not self.approved or not self.output_path:
                raise ReviewError(
                    409, "The anonymized file is not ready yet.")
            return self.output_path, (
                self.content_type
                if self.kind == "image" else "video/mp4")

    def reject(self, version):
        """Guarda a versão rejeitada e gera a seguinte com as observações."""
        with self.lock:
            self._require_document()
            if version.attempt != self.attempt:
                raise ReviewError(409, "The version under review has "
                                       "already changed.")
            reasons = list(self.reasons)
            if version.reason.strip():
                reasons.append(version.reason.strip())
            censored = None
            if self.kind == "audio":
                result, censored = self._run_audio(
                    self._original, self.lines, self._word_times, reasons,
                    self._folder, self.attempt + 1, self.initial)
            else:
                result = self._run(self.lines, reasons, self.initial)
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
                raise ReviewError(409, "The version under review has "
                                       "already changed.")
            reasons = list(self.reasons)
            if version.reason.strip():
                reasons.append(version.reason.strip())
            instructions = build_instructions(reasons, self.initial)
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
                "pdf_url": PDF_URL if self.source_pdf else None,
                "audio_ranges": (
                    len(result["ranges"])
                    if self.kind == "audio" and result else 0),
                "audio_enabled": self.audio_enabled(),
                "attempt": self.attempt,
                "text": self.text,
                "original_text": "\n".join(self.lines) if self.lines else "",
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
            raise ReviewError(409, "There is no document yet.")

    def _require_media(self):
        if self.kind not in {"image", "video"} or self.source_path is None:
            raise ReviewError(409, "There is no image or video yet.")

    def _require_media_ready(self):
        self._require_media()
        if self.status != "ready":
            raise ReviewError(
                409, "The image or video analysis has not finished yet.")

    def _set(self, result):
        self.result = result
        self.text = "\n".join(result["masked"])

    def _run(self, lines, reasons, initial=None):
        instructions = build_instructions(reasons, initial)
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

    def _run_audio(self, original, lines, times, reasons, folder, number,
                   initial=None):
        """Deteta e censura. Devolve ``(resultado, áudio_censurado)``."""
        instructions = build_instructions(reasons, initial)
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


def build_instructions(reasons, initial=None):
    """Junta as instruções do utilizador num texto para o modelo.

    ``initial`` é o que o utilizador escreveu ao enviar o ficheiro e vai
    sempre, em primeiro lugar. Depois vêm as observações do revisor
    (``reasons``): cabem no máximo ``pipeline.MAX_INSTRUCTIONS`` caracteres no
    total e, se não couberem todas, ficam as mais recentes. Devolve ``None``
    sem nenhuma das duas.
    """
    kept = []
    size = len(INSTRUCTIONS_HEADER)
    if initial:
        size += len(initial) + 2
    for reason in reversed(reasons):
        size += len(reason) + 3
        if size > pipeline.MAX_INSTRUCTIONS:
            if not kept:
                raise ReviewError(
                    422, "The feedback does not fit, with the initial "
                         "instructions, in the %d-character limit."
                    % pipeline.MAX_INSTRUCTIONS)
            break
        kept.append(reason)
    parts = []
    if initial:
        parts.append(initial)
    if kept:
        parts.append("\n- ".join(
            [INSTRUCTIONS_HEADER] + list(reversed(kept))))
    return "\n\n".join(parts) or None


def initial_instructions(header):
    """As instruções iniciais do cabeçalho ``X-User-Instructions``.

    Vêm em percent-encoding (como o nome do ficheiro) para caberem num
    cabeçalho. Devolve ``None`` se faltarem ou estiverem em branco; levanta
    ``ReviewError`` (422) se passarem de ``MAX_INITIAL_INSTRUCTIONS``.
    """
    text = unquote(header or "").strip()
    if not text:
        return None
    if len(text) > MAX_INITIAL_INSTRUCTIONS:
        raise ReviewError(422, INITIAL_TOO_LONG)
    return text


def lines_from_upload(content_type, body):
    """Linhas do documento enviado (PDF ou texto UTF-8)."""
    if len(body) > MAX_DOCUMENT_BYTES:
        raise ReviewError(413, "The document is too large.")
    kind = content_type.split(";")[0].strip().lower()
    if kind == "application/pdf":
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            path = Path(folder) / "documento.pdf"
            path.write_bytes(body)
            try:
                return pipeline.read_lines(path)
            except (RuntimeError, OSError):
                raise ReviewError(
                    422, "The PDF could not be read.") from None
    if kind == "text/plain":
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            raise ReviewError(
                422, "The text must be UTF-8.") from None
        import pdf_extractor
        text = pdf_extractor.remove_empty_lines(text)
        return detection.normalize_lines(text.split("\n")) if text else []
    raise ReviewError(415, "Send a PDF or plain text (UTF-8).")


AUDIO_ONLY_CONTAINERS = {
    "video/mp4": "audio/mp4",
    "video/quicktime": "audio/mp4",
}
PROBE_TIMEOUT = 20


def audio_only_video(content_type, body):
    """Diz se um "vídeo" enviado é só áudio.

    Uma gravação do telemóvel ou do WhatsApp só com som costuma chegar com a
    extensão ``.mp4`` ou ``.mov``, e o navegador di-la ``video/mp4``. O
    ``ffprobe`` vê se há mesmo imagem (uma capa de álbum não conta). Sem o
    ``ffprobe`` ou se não conseguir ler o ficheiro, trata-se como vídeo, que é
    o que fazia antes.
    """
    kind = content_type.split(";")[0].strip().lower()
    if kind not in AUDIO_ONLY_CONTAINERS or len(body) > MAX_AUDIO_BYTES:
        return False
    if shutil.which("ffprobe") is None:
        return False
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        path = Path(folder) / "probe"
        path.write_bytes(body)
        try:
            done = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries",
                 "stream=codec_type:stream_disposition=attached_pic",
                 "-of", "json", str(path)],
                capture_output=True, timeout=PROBE_TIMEOUT, check=False)
            streams = json.loads(done.stdout or b"{}").get("streams", [])
        except (OSError, subprocess.SubprocessError, ValueError):
            return False
    if done.returncode != 0 or not streams:
        return False
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    has_picture = any(
        s.get("codec_type") == "video"
        and not s.get("disposition", {}).get("attached_pic")
        for s in streams)
    return has_audio and not has_picture


def audio_suffix(content_type, body):
    """Extensão do áudio enviado, validando o tipo e o tamanho."""
    if len(body) > MAX_AUDIO_BYTES:
        raise ReviewError(413, "The audio is too large.")
    kind = content_type.split(";")[0].strip().lower()
    if kind not in AUDIO_TYPES:
        raise ReviewError(415, "Send mp3, m4a or wav audio.")
    if not body:
        raise ReviewError(422, "The audio is empty.")
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
        allow_headers=[
            "Content-Type", "X-File-Name", "X-User-Instructions"],
    )
    app.state.session = session
    atexit.register(session.close)

    @app.exception_handler(ReviewError)
    async def review_error(_request, error):
        return JSONResponse(
            {"detail": error.message}, status_code=error.status)

    @app.post("/api/document")
    async def upload(request: Request):
        initial = initial_instructions(
            request.headers.get("x-user-instructions"))
        body = await request.body()
        content_type = request.headers.get("content-type", "")
        if await run_in_threadpool(audio_only_video, content_type, body):
            # An audio recording named .mp4: it goes the audio way.
            suffix = audio_suffix(
                AUDIO_ONLY_CONTAINERS[
                    content_type.split(";")[0].strip().lower()], body)
            await run_in_threadpool(
                session.load_audio, body, suffix, initial)
            return session.snapshot()
        if supported_media_kind(content_type):
            session.load_media(
                body, content_type,
                request.headers.get("x-file-name", "media"), initial)
            return session.snapshot()
        lines = lines_from_upload(content_type, body)
        is_pdf = content_type.split(";")[0].strip().lower() == (
            "application/pdf")
        await run_in_threadpool(
            session.load, lines, initial, body if is_pdf else None)
        return session.snapshot()

    @app.post("/api/audio")
    async def upload_audio(request: Request):
        initial = initial_instructions(
            request.headers.get("x-user-instructions"))
        body = await request.body()
        suffix = audio_suffix(request.headers.get("content-type", ""), body)
        await run_in_threadpool(session.load_audio, body, suffix, initial)
        return session.snapshot()

    @app.get("/api/pdf/current")
    async def current_pdf():
        path = await run_in_threadpool(session.pdf_path)
        return FileResponse(
            path, media_type="application/pdf",
            filename="documento_anonimizado.pdf",
            headers={"Cache-Control": "no-store"})

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

    @app.post("/api/media/preview")
    async def media_preview(request: PreviewRequest):
        data = await run_in_threadpool(session.preview_media, request)
        return Response(
            content=data, media_type="image/jpeg",
            headers={"Cache-Control": "no-store"})

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
