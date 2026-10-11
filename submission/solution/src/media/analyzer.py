"""Visual PII detector backed by the Cloudflare Gemini gateway.

The local review server never reads a Gemini credential. It sends sampled
JPEG frames to the Worker, which turns them into genuine Gemini ``inlineData``
parts and enforces the structured-output schema at the trust boundary.
"""

from __future__ import annotations

import base64
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from categories import CATEGORY_NAMES, CONFIDENCE_LEVELS

from .capabilities import MediaModel
from .regions import Box, MediaRegion, RegionKeyframe, padded_box


MEDIA_PROMPT = """You are inspecting images for visual personal-data
redaction. Find EVERY visible region that identifies, links to, or profiles a
natural person. This includes faces; names; home addresses and postal codes;
Citizen Cards, student cards, passports, driving licences and other identity
documents;
identity, tax, social-security, employee, student and customer numbers;
telephone numbers, email addresses and usernames; vehicle plates; signatures;
fingerprints and other biometrics; payment or bank data; QR codes and barcodes;
badges, mail labels and screens; and visible medical, genetic, religious,
political, family, behavioural or employment information.

Cover an entire identity document, payment card, badge, signature, fingerprint,
vehicle plate, QR/barcode, mail label or screen whenever masking only part
could leak information. For faces, return a TIGHT box around the face itself:
include eyes, nose, mouth and chin, but exclude hair, neck, shoulders, body
and empty background. Each face must have its own box; never return the whole
image as a face box. Interpret objects in the context of the whole scene.
A face requires recognizable facial structure; do not infer faces from fingers,
shadows, clothing, furniture or background textures. Detect personal data
supported by visible evidence, rather than assuming every object is sensitive.
Use confidence "incerto" for ambiguous evidence. Do not return separate regions
for information already covered by an entire document or card region. If no
personal data is visible, return an empty detections list. Do not return the
sensitive text itself. Images are labelled with a numeric frame_id. Inspect
each frame independently: moving objects need new bounds in each frame, even
when it is the same object. Never copy coordinates from a previous frame.
box_2d is [ymin, xmin, ymax, xmax], using integers from 0 to 1000.
Write every reason in English, as one short generic sentence (what kind of
item it is and why it identifies a person), never quoting the sensitive text.
"""

RESIDUAL_PROMPT = MEDIA_PROMPT + """
These images already contain strong pixelated redactions.
Find any personal or sensitive visual information that remains visible. Do not
return regions that are already fully pixelated or mistake pixelation artifacts
for faces or personal data. Use the same contract and
never return the sensitive text itself."""

MEDIA_ANALYZE_PATH = "/api/v1/media/analyze"
MEDIA_CAPABILITIES_PATH = "/api/v1/media/capabilities"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
RETRY_STATUS = (408, 429, 500, 502, 503, 504)
USER_AGENT = "nos-anonymizer/1.0"


class ProviderDetection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    frame_id: int = Field(ge=0)
    box_2d: list[int] = Field(min_length=4, max_length=4)
    category: str
    kind: str
    reason: str = Field(min_length=1, max_length=240)
    confidence: str


class ProviderBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    detections: list[ProviderDetection]


class MediaAnalysisError(Exception):
    """The gateway/provider failed or returned an unsafe response."""


class GeminiMediaAnalyzer:
    """Compatibility name for the Gemini analyzer routed via Cloudflare."""

    def __init__(
        self,
        model: MediaModel,
        *,
        gateway_url: str,
        origin: str,
        timeout: float = 90.0,
        attempts: int = 3,
        delay: float = 1.0,
        opener: Any = urllib.request.urlopen,
        sleep: Any = time.sleep,
    ):
        self.model = model
        self.base_url = _base_url(gateway_url)
        self.origin = origin.strip()
        if not self.origin:
            raise MediaAnalysisError(
                "Media model is not configured or does not support "
                "image/video.")
        self.timeout = timeout
        self.attempts = max(1, attempts)
        self.delay = delay
        self.opener = opener
        self.sleep = sleep
        self._verified: MediaModel | None = None

    def close(self):
        return None

    def verify(self) -> MediaModel:
        """Ask the Worker to verify the allowlisted model with Gemini."""

        if self._verified is not None:
            return self._verified
        value = self._request(MEDIA_CAPABILITIES_PATH, method="GET")
        try:
            remote = value["model"]
            model = MediaModel(
                id=remote["id"],
                capabilities=tuple(remote["capabilities"]),
                verified=remote["verified"] is True,
            )
        except (KeyError, TypeError):
            raise MediaAnalysisError(
                "Media model identity could not be verified.") from None
        expected = MediaModel(
            self.model.id, self.model.capabilities, verified=True)
        if model != expected:
            raise MediaAnalysisError(
                "Media model identity could not be verified.")
        self._verified = model
        return model

    def analyze(self, frames, *, residual=False, instructions=None):
        """Analyze ``[(frame_id, jpeg_bytes)]`` through the Worker."""

        self.verify()
        prompt = RESIDUAL_PROMPT if residual else MEDIA_PROMPT
        if instructions:
            prompt += "\nReviewer instructions:\n" + instructions[:2000]
        allowed_ids = {frame_id for frame_id, _ in frames}
        body = {
            "prompt": prompt,
            "frames": [
                {
                    "frame_id": frame_id,
                    "mime_type": "image/jpeg",
                    "data": base64.b64encode(data).decode("ascii"),
                }
                for frame_id, data in frames
            ],
        }
        value = self._request(MEDIA_ANALYZE_PATH, body=body, method="POST")
        try:
            batch = ProviderBatch.model_validate(value)
        except (ValidationError, ValueError, TypeError):
            raise MediaAnalysisError(
                "Media model returned an invalid structured "
                "response.") from None
        return [
            _to_region(item) for item in batch.detections
            if item.frame_id in allowed_ids
        ]

    def _request(self, path, *, body=None, method="POST"):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Origin": self.origin,
                "User-Agent": USER_AGENT,
                **({"Content-Type": "application/json"} if data else {}),
            },
        )
        for attempt in range(1, self.attempts + 1):
            try:
                with self.opener(request, timeout=self.timeout) as response:
                    raw = response.read()
                return json.loads(raw.decode("utf-8"))
            except urllib.error.HTTPError as error:
                status = error.code
                error.close()
                if status not in RETRY_STATUS:
                    raise MediaAnalysisError(
                        "Media gateway rejected the request.") from None
            except (socket.timeout, TimeoutError, urllib.error.URLError,
                    OSError):
                pass
            except (ValueError, UnicodeDecodeError):
                raise MediaAnalysisError(
                    "Media gateway returned an invalid response.") from None
            if attempt < self.attempts:
                self.sleep(self.delay * attempt)
        raise MediaAnalysisError(
            "Media model could not analyze the visual content.")


def _base_url(url):
    value = url.strip().rstrip("/")
    parts = urllib.parse.urlsplit(value)
    if (parts.scheme not in ("http", "https") or not parts.hostname or
            (parts.scheme == "http" and parts.hostname not in LOCAL_HOSTS)):
        raise MediaAnalysisError(
            "Media model is not configured or does not support image/video.")
    return value


def _to_region(item: ProviderDetection) -> tuple[int, MediaRegion]:
    if item.category not in CATEGORY_NAMES:
        raise MediaAnalysisError("Media model returned an unknown category.")
    if item.confidence not in CONFIDENCE_LEVELS:
        raise MediaAnalysisError("Media model returned invalid confidence.")
    ymin, xmin, ymax, xmax = item.box_2d
    values = (ymin, xmin, ymax, xmax)
    if any(not isinstance(value, int) or not 0 <= value <= 1000
           for value in values) or ymin >= ymax or xmin >= xmax:
        raise MediaAnalysisError("Media model returned an invalid box.")
    kind = item.kind if item.kind in {
        "face", "text", "identity_document", "plate", "signature",
        "biometric", "code", "other",
    } else "other"
    box = padded_box(Box(
        x=xmin / 1000, y=ymin / 1000,
        width=(xmax - xmin) / 1000,
        height=(ymax - ymin) / 1000,
    ), 0.02 if kind == "face" else 0.12)
    region = MediaRegion(
        category=item.category,
        kind=kind,
        reason=item.reason,
        confidence=item.confidence,
        source="gemini",
        start_ms=0,
        end_ms=0,
        keyframes=[RegionKeyframe(time_ms=0, box=box)],
    )
    return item.frame_id, region
