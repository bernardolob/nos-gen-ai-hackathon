"""Secure FastAPI boundary around the Gemini sensitive-entity client."""

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
from pydantic import Field, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .api_config import ApiSettings
from .client import MODEL_ID, GeminiClient
from .config import GeminiSettings
from .errors import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    GeminiConnectionError,
    GeminiRequestError,
    GeminiServiceError,
    GeminiTimeoutError,
    InvalidInputError,
    ModelMismatchError,
    ModelUnavailableError,
    RateLimitError,
    ResponseValidationError,
)
from .models import DetectionResult, StrictModel, TextBlock

LOGGER = logging.getLogger("nos_anonymizer.api")
bearer_scheme = HTTPBearer(auto_error=False)

READINESS_FAILURES = (
    AuthenticationError,
    AuthorizationError,
    GeminiConnectionError,
    GeminiRequestError,
    GeminiServiceError,
    GeminiTimeoutError,
    ModelMismatchError,
    ModelUnavailableError,
    RateLimitError,
    ResponseValidationError,
)
TRANSIENT_DETECTION_FAILURES = (
    AuthenticationError,
    AuthorizationError,
    GeminiConnectionError,
    GeminiServiceError,
    GeminiTimeoutError,
    ModelUnavailableError,
    RateLimitError,
)


class HealthResponse(StrictModel):
    status: str


class ReadyResponse(StrictModel):
    status: str
    model: str


class DetectionBlockRequest(StrictModel):
    block_id: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, repr=False)


class DetectionRequest(StrictModel):
    blocks: tuple[DetectionBlockRequest, ...] = Field(min_length=1)


class RequestSizeLimitMiddleware:
    """Reject oversized detection bodies and replay accepted ASGI messages."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") != "/api/v1/detect":
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
                    content={"detail": "Request body exceeds the configured limit."},
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
    """Resolve the lifespan-owned client; tests may override this dependency."""

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
    valid = bool(expected) and hmac.compare_digest(supplied_digest, expected_digest)
    valid = valid and credentials is not None and credentials.scheme.lower() == "bearer"
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing backend credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _validate_limits(payload: DetectionRequest, settings: ApiSettings) -> None:
    if len(payload.blocks) > settings.max_block_count:
        raise HTTPException(
            status_code=422,
            detail="Request contains too many blocks.",
        )
    block_ids = [block.block_id for block in payload.blocks]
    if len(block_ids) != len(set(block_ids)):
        raise HTTPException(
            status_code=422,
            detail="Block IDs must be unique.",
        )
    if any(len(block.text) > settings.max_text_length for block in payload.blocks):
        raise HTTPException(
            status_code=422,
            detail="A text block exceeds the configured limit.",
        )


def _request_id_from(_request: Request) -> str:
    return str(uuid4())


def _secure_response(
    response: Response,
    request_id: str,
    *,
    production: bool,
) -> Response:
    response.headers["X-Request-ID"] = request_id
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    if production:
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
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
        title="NOS Anonymizer API",
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
        request_id = _request_id_from(request)
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
        _error: Exception,
    ) -> JSONResponse:
        LOGGER.error(
            "Unhandled API error request_id=%s",
            getattr(request.state, "request_id", "unavailable"),
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
        except READINESS_FAILURES:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Gemini readiness check failed.",
            ) from None
        return ReadyResponse(status="ready", model=MODEL_ID)

    @app.post(
        "/api/v1/detect",
        response_model=DetectionResult,
        dependencies=protected,
    )
    async def detect(
        payload: DetectionRequest,
        request: Request,
        client: Annotated[GeminiClient, Depends(get_gemini_client)],
    ) -> DetectionResult:
        _validate_limits(payload, request.app.state.api_settings)
        try:
            blocks = tuple(
                TextBlock(block_id=block.block_id, text=block.text)
                for block in payload.blocks
            )
        except ValidationError:
            raise HTTPException(
                status_code=422,
                detail="Detection input is invalid.",
            ) from None
        try:
            return await run_in_threadpool(client.detect_sensitive_entities, blocks)
        except InvalidInputError:
            raise HTTPException(
                status_code=422,
                detail="Detection input is invalid.",
            ) from None
        except (ResponseValidationError, ModelMismatchError):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Gemini returned an invalid response.",
            ) from None
        except TRANSIENT_DETECTION_FAILURES:
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
