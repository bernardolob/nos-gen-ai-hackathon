# Gemini integration

This milestone provides a text-only boundary around the Google Gemini API. It
detects sensitive entities but deliberately does not read files, perform OCR,
or redact content.

## Architecture

```text
Future source adapters (JSON, PDF, OCR, image, video, audio, Office)
                              |
                              v
              TextBlock(block_id, text, metadata)
                              |
                              v
                         GeminiClient
                              |
                              v
            validated, redaction-ready SensitiveEntity spans
                              |
                              v
                 future deterministic redaction layer
```

Adapters own parsing, downloading, storage, media conversion, and provenance.
They convert source material to `TextBlock` instances. Adapter metadata is kept
locally and is not transmitted to Gemini. The stable block ID connects each
returned entity to its original source location.

The client API is synchronous and intentionally small:

```python
from nos_anonymizer import GeminiClient, GeminiSettings, TextBlock

blocks = [
    TextBlock(
        block_id="page:1:paragraph:2",
        text="Contacte Maria Silva através de maria@example.test.",
        metadata={"page": 1},
    )
]

with GeminiClient(GeminiSettings.from_env()) as client:
    token_count = client.count_tokens(blocks)
    result = client.detect_sensitive_entities(blocks)

for entity in result.entities:
    assert blocks[0].text[entity.start_char:entity.end_char] == entity.text
```

Offsets are zero-based, half-open Python Unicode code-point offsets. Responses
are checked against a Pydantic schema and then checked semantically against the
original blocks. Unknown blocks, invalid offsets, mismatched text, duplicates,
overlaps, missing usage data, and observable model mismatches fail closed.

## Authentication and configuration

Create a new key in [Google AI Studio](https://aistudio.google.com/) and expose
it only through the process environment:

```powershell
$env:GEMINI_API_KEY = "your-new-key"
nos-gemini-check
```

```bash
export GEMINI_API_KEY="your-new-key"
nos-gemini-check
```

Do not put a real key in `.env.example`, source code, command-line arguments,
notebooks, test fixtures, logs, or screenshots. If a key is pasted into chat or
committed, revoke it and rotate it immediately. The application never includes
the key or source text in its own exceptions.

Operational settings are optional:

| Variable | Default | Accepted range |
| --- | ---: | ---: |
| `GEMINI_TIMEOUT_SECONDS` | 60 | greater than 0, at most 600 |
| `GEMINI_RETRY_ATTEMPTS` | 3 | 1–10, including the first request |
| `GEMINI_RETRY_INITIAL_DELAY_SECONDS` | 1 | 0–60 |
| `GEMINI_RETRY_MAX_DELAY_SECONDS` | 8 | 0–120 |

Retries apply only to HTTP 408, 429, 500, 502, 503, and 504 responses. Invalid
credentials, permissions, input, model identity, and model output are not
retried. The count operation counts the system instruction and serialized
blocks; detection reports actual input, output, thought, and total usage.

## Data handling and model policy

Detection uses the Interactions API with `store=False`. This matters because
Interactions are otherwise stored by default. Do not enable SDK HTTP debugging
in environments processing sensitive content. Google may still process and
retain data according to the applicable Gemini API terms; review those terms
before sending production personal data.

The model identifier is a code constant, not configuration:

```text
gemini-3.5-flash
```

The client never retries against or falls back to another model. It also rejects
a different model identity if Google exposes one in the response. However,
Google's documentation currently marks this identifier deprecated and states
that the provider automatically routes it to Gemini 3.6 Flash. The client cannot
detect or prevent routing hidden behind the same provider identifier. See the
[Gemini 3.5 Flash notice](https://ai.google.dev/gemini-api/docs/whats-new-gemini-3.5)
and [Interactions data-retention documentation](https://ai.google.dev/gemini-api/docs/interactions-overview).

## What is intentionally absent

This milestone contains no file ingestion, JSON traversal, PDF parsing, OCR,
image conversion, media upload, video frame extraction, audio processing,
Office parsing, masking, n8n workflow, or submission generation. Those features
belong in adapters or downstream deterministic processing and must not be added
to `GeminiClient`.
