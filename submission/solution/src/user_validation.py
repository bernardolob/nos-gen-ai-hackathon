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
import tempfile
import threading
from pathlib import Path

import detection
import gateway
import pipeline
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

HOST = "127.0.0.1"
PORT = 8000
MAX_DOCUMENT_BYTES = 10_000_000
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


class RejectedVersion(BaseModel):
    attempt: int
    text: str
    reason: str = ""


class ReviewError(Exception):
    """Erro de uso da revisão; ``status`` é o código HTTP e ``message`` é
    seguro de mostrar (nunca inclui o documento)."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


class ReviewSession:
    """A revisão em curso: documento, tentativa atual e histórico."""

    def __init__(self, generate=None):
        self.generate = generate
        self.lock = threading.Lock()
        self._reset()

    def _reset(self):
        self.lines = []
        self.attempt = 1
        self.text = ""
        self.history = []
        self.reasons = []
        self.result = None
        self.approved = False

    def load(self, lines):
        """Começa uma revisão nova com o documento dado."""
        if not any(line.strip() for line in lines):
            raise ReviewError(422, "O documento não tem texto.")
        with self.lock:
            result = self._run(lines, [])
            self._reset()
            self.lines = lines
            self._set(result)

    def reject(self, version):
        """Guarda a versão rejeitada e gera a seguinte com as observações."""
        with self.lock:
            self._require_document()
            if version.attempt != self.attempt:
                raise ReviewError(409, "A versão em revisão já mudou.")
            reasons = list(self.reasons)
            if version.reason.strip():
                reasons.append(version.reason.strip())
            result = self._run(self.lines, reasons)
            self.history.append(RejectedVersion(
                attempt=self.attempt, text=self.text,
                reason=version.reason.strip()))
            self.reasons = reasons
            self.attempt += 1
            self._set(result)

    def approve(self):
        with self.lock:
            self._require_document()
            self.approved = True

    def snapshot(self):
        with self.lock:
            result = self.result
            return {
                "has_document": bool(self.lines),
                "attempt": self.attempt,
                "text": self.text,
                "approved": self.approved,
                "history": [v.model_dump() for v in self.history],
                "mode": "model" if self.generate else "rules",
                "warnings": len(result["warnings"]) if result else 0,
                "issues": len(result["issues"]) if result else 0,
            }

    def _require_document(self):
        if not self.lines:
            raise ReviewError(409, "Ainda não há nenhum documento.")

    def _set(self, result):
        self.result = result
        self.text = "\n".join(result["masked"])

    def _run(self, lines, reasons):
        instructions = build_instructions(reasons)
        try:
            return pipeline.run(lines, self.generate, instructions)
        except (detection.DetectionError, gateway.GatewayError):
            raise ReviewError(502, MODEL_FAILED) from None


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


def allowed_origins(environ=None):
    env = os.environ if environ is None else environ
    value = env.get("REVIEW_UI_ORIGINS", "")
    origins = [o.strip().rstrip("/") for o in value.split(",") if o.strip()]
    if "*" in origins:
        raise ValueError("REVIEW_UI_ORIGINS não pode conter *.")
    return origins or list(DEFAULT_ORIGINS)


def create_app(generate=None, origins=None):
    """Cria a aplicação; ``generate`` é o modelo (None = só as regras)."""
    app = FastAPI(title="Revisão de anonimização")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or allowed_origins(),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    session = ReviewSession(generate)
    app.state.session = session

    @app.exception_handler(ReviewError)
    async def review_error(_request, error):
        return JSONResponse(
            {"detail": error.message}, status_code=error.status)

    @app.post("/api/document")
    async def upload(request: Request):
        body = await request.body()
        lines = lines_from_upload(
            request.headers.get("content-type", ""), body)
        await run_in_threadpool(session.load, lines)
        return session.snapshot()

    @app.get("/api/current")
    def current():
        return session.snapshot()

    @app.post("/api/reject")
    def reject(version: RejectedVersion):
        session.reject(version)
        return session.snapshot()

    @app.post("/api/approve")
    def approve():
        session.approve()
        return {"status": "approved", **session.snapshot()}

    return app


def main():
    import uvicorn
    app = create_app(gateway.from_env())
    print("Revisão em http://%s:%d (%s)" % (
        HOST, PORT, "com o Gemini" if app.state.session.generate
        else "só regras de segurança"))
    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
