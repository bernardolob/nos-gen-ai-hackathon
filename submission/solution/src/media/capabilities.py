"""Configuration boundary for models allowed to inspect visual media."""

from __future__ import annotations

import os
from dataclasses import dataclass


REQUIRED_CAPABILITIES = ("image", "video", "structured_output")

# Keep this deliberately explicit. Adding a model is a reviewed decision, not
# a prefix match which could accidentally admit a text-only deployment.
MEDIA_CAPABILITIES = {
    "gemini-3.5-flash-lite": REQUIRED_CAPABILITIES,
    "gemini-3.5-flash": REQUIRED_CAPABILITIES,
    "gemini-3.6-flash": REQUIRED_CAPABILITIES,
    "gemini-3.7-flash": REQUIRED_CAPABILITIES,
    "gemini-3.8-flash": REQUIRED_CAPABILITIES,
}
DEFAULT_MEDIA_MODEL = "gemini-3.5-flash-lite"


class MediaConfigurationError(Exception):
    """The configured provider cannot safely process visual media."""


@dataclass(frozen=True)
class MediaModel:
    id: str
    capabilities: tuple[str, ...]
    verified: bool = False

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "capabilities": list(self.capabilities),
            "verified": self.verified,
        }


def media_model_from_env(environ=None) -> MediaModel:
    """Resolve an allowlisted model configured on the Cloudflare gateway.

    The local process deliberately does not accept ``GEMINI_API_KEY`` as a
    media credential. Media inference must cross the server-held secret
    boundary used by text inference.
    """

    env = os.environ if environ is None else environ
    model_id = env.get("GEMINI_MEDIA_MODEL", DEFAULT_MEDIA_MODEL).strip()
    capabilities = MEDIA_CAPABILITIES.get(model_id)
    if capabilities != REQUIRED_CAPABILITIES:
        raise MediaConfigurationError(
            "Media model is not configured or does not support image/video."
        )
    if not env.get("GEMINI_GATEWAY_URL", "").strip() or not env.get(
            "GEMINI_GATEWAY_ORIGIN", "").strip():
        raise MediaConfigurationError(
            "Media model is not configured or does not support image/video."
        )
    return MediaModel(model_id, capabilities)
