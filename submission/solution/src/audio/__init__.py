"""Extra: censura de áudio (transcrição, alinhamento, redação).

Ver ``AUDIO.md`` para a arquitetura e as decisões.
"""

from .alignment import AlignmentError, find_masked_ranges
from .elevenlabs_client import ConfigurationError, ScribeRequestError
from .elevenlabs_client import from_env as scribe_from_env
from .redactor import RedactionError, redact
from .transcriber import TranscriptionError, transcribe

__all__ = [
    "AlignmentError",
    "ConfigurationError",
    "RedactionError",
    "ScribeRequestError",
    "TranscriptionError",
    "find_masked_ranges",
    "redact",
    "scribe_from_env",
    "transcribe",
]
