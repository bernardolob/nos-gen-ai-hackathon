"""Minimal, non-generating Gemini connection check."""

import argparse
import sys
from collections.abc import Sequence

from .client import GeminiClient
from .config import GeminiSettings
from .errors import ConfigurationError, GeminiIntegrationError


def _parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        prog="nos-gemini-check",
        description="Check Gemini authentication and pinned-model availability.",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the connection check and return a process exit code."""

    _parser().parse_args(argv)
    try:
        settings = GeminiSettings.from_env()
    except ConfigurationError:
        print(
            "Configuration error: set a valid GEMINI_API_KEY environment variable.",
            file=sys.stderr,
        )
        return 2

    try:
        with GeminiClient(settings) as client:
            info = client.check_connection()
    except GeminiIntegrationError as exc:
        print(f"Connection check failed: {exc}", file=sys.stderr)
        return 3

    print(f"Connection successful: {info.requested_model} is accessible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
