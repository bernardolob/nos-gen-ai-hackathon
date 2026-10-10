"""Secure FastAPI boundary around the Gemini client."""

from __future__ import annotations

import hashlib
import hmac
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import field_validator
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from gemini import (
    MODEL_ID,
    BadResponseError,
    ConfigurationError,
    GeminiClient,
    GeminiRequestError,
    GeminiSettings,
    GenerationResult,
    InvalidInputError,
    StrictModel,
    UnavailableError,
    UpstreamError,
)

from .settings import ApiSettings

LOGGER = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)

GENERATE_PATH = "/api/v1/generate"
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}
HSTS_HEADER = "max-age=31536000; includeSubDomains"


class HealthResponse(StrictModel):
    status: str


class ReadyResponse(StrictModel):
    status: str
    model: str


class GenerationRequest(StrictModel):
    prompt: str

    @field_validator("prompt")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must contain text")
        return value


class RequestSizeLimitMiddleware:
    """Reject oversized bodies on one path and replay accepted messages."""

    def __init__(self, app: ASGIApp, max_bytes: int, path: str) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.path = path

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http" or scope.get("path") != self.path:
            await self.app(scope, receive, send)
            return

        messages: list[Message] = []
        size = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                await self.app(scope, _message_receiver(messages), send)
                return
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                response = JSONResponse(
                    status_code=422,
                    content={
                        "detail": "Request body exceeds the configured limit."
                    },
                )
                await response(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        await self.app(scope, _message_receiver(messages), send)


def _message_receiver(messages: list[Message]) -> Receive:
    iterator = iter(messages)

    async def receive() -> Message:
        try:
            return next(iterator)
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}

    return receive


def get_gemini_client(request: Request) -> GeminiClient:
    """Resolve the lifespan-owned client; tests may override this."""

    client = getattr(request.app.state, "gemini_client", None)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backend configuration is missing or invalid.",
        )
    return client


def _require_backend_token(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> None:
    configured = request.app.state.api_settings.backend_api_token
    supplied = credentials.credentials if credentials is not None else ""
    expected = configured.get_secret_value() if configured is not None else ""
    supplied_digest = hashlib.sha256(supplied.encode("utf-8")).digest()
    expected_digest = hashlib.sha256(expected.encode("utf-8")).digest()
    valid = bool(expected) and hmac.compare_digest(
        supplied_digest,
        expected_digest,
    )
    valid = (
        valid
        and credentials is not None
        and credentials.scheme.lower() == "bearer"
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing backend credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _secure_response(
    response: Response,
    request_id: str,
    *,
    production: bool,
) -> Response:
    response.headers.update(SECURITY_HEADERS)
    response.headers["X-Request-ID"] = request_id
    if production:
        response.headers["Strict-Transport-Security"] = HSTS_HEADER
    return response


def create_app(
    api_settings: ApiSettings | None = None,
    *,
    client_factory: Callable[[GeminiSettings], GeminiClient] = GeminiClient,
) -> FastAPI:
    """Build the application without performing provider I/O."""

    settings = api_settings or ApiSettings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.gemini_client = None
        try:
            gemini_settings = GeminiSettings.from_env()
            app.state.gemini_client = client_factory(gemini_settings)
        except ConfigurationError:
            pass
        try:
            yield
        finally:
            client = app.state.gemini_client
            if client is not None:
                await run_in_threadpool(client.close)

    app = FastAPI(
        title="NOS Gemini Gateway API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url=None if settings.production else "/docs",
        redoc_url=None if settings.production else "/redoc",
        openapi_url=None if settings.production else "/openapi.json",
    )
    app.state.api_settings = settings
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=settings.max_request_bytes,
        path=GENERATE_PATH,
    )
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )

    @app.middleware("http")
    async def security_boundary(
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        request_id = str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        return _secure_response(
            response,
            request_id,
            production=request.app.state.api_settings.production,
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": "Request validation failed."},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request,
        error: Exception,
    ) -> JSONResponse:
        LOGGER.error(
            "Unhandled API error request_id=%s error_type=%s",
            getattr(request.state, "request_id", "unavailable"),
            type(error).__name__,
        )
        response = JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error."},
        )
        return _secure_response(
            response,
            getattr(request.state, "request_id", str(uuid4())),
            production=request.app.state.api_settings.production,
        )

    protected = [Depends(_require_backend_token)]

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get(
        "/ready",
        response_model=ReadyResponse,
        dependencies=protected,
    )
    async def ready(
        client: Annotated[GeminiClient, Depends(get_gemini_client)],
    ) -> ReadyResponse:
        try:
            await run_in_threadpool(client.check_connection)
        except UpstreamError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Gemini readiness check failed.",
            ) from None
        return ReadyResponse(status="ready", model=MODEL_ID)

    @app.post(
        GENERATE_PATH,
        response_model=GenerationResult,
        dependencies=protected,
    )
    async def generate(
        payload: GenerationRequest,
        request: Request,
        client: Annotated[GeminiClient, Depends(get_gemini_client)],
    ) -> GenerationResult:
        max_length = request.app.state.api_settings.max_prompt_length
        if len(payload.prompt) > max_length:
            raise HTTPException(
                status_code=422,
                detail="Prompt exceeds the configured limit.",
            )
        try:
            return await run_in_threadpool(
                client.generate_text,
                payload.prompt,
            )
        except InvalidInputError:
            raise HTTPException(
                status_code=422,
                detail="Generation input is invalid.",
            ) from None
        except BadResponseError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini returned an invalid response.",
            ) from None
        except UnavailableError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Gemini is temporarily unavailable.",
            ) from None
        except GeminiRequestError:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini rejected the backend request.",
            ) from None

    return app


app = create_app()
