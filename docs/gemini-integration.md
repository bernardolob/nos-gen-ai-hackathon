# Gemini connection integration

The package creates a secure Python connection to Google Gemini and uses exactly
`gemini-3.5-flash`.

`check_connection()` retrieves model metadata. `generate_text()` can send plain
text and returns a validated `GenerationResult`. Neither method reads files,
processes PDFs, performs OCR, stores data, or anonymizes documents.

## Usage

Create a new Gemini API key and expose it only through the environment:

```powershell
$env:GEMINI_API_KEY = "your-new-key"
nos-gemini-check
```

```bash
export GEMINI_API_KEY="your-new-key"
nos-gemini-check
```

The equivalent Python interface is:

```python
from nos_anonymizer import GeminiClient, GeminiSettings

with GeminiClient(GeminiSettings.from_env()) as client:
    model_info = client.check_connection()

print(model_info.requested_model)
```

`check_connection()` requests model metadata and validates the returned model
identity and optional token-limit metadata. It does not generate any content.

To generate text after the explicit caller has supplied it:

```python
with GeminiClient(GeminiSettings.from_env()) as client:
    result = client.generate_text("say hi")

print(result.text)
```

The API key remains an environment-only credential and the model ID is pinned.

## Configuration

| Variable | Default | Accepted range |
| --- | ---: | ---: |
| `GEMINI_API_KEY` | required | non-empty |
| `GEMINI_TIMEOUT_SECONDS` | 60 | greater than 0, at most 600 |
| `GEMINI_RETRY_ATTEMPTS` | 3 | 1–10, including the first request |
| `GEMINI_RETRY_INITIAL_DELAY_SECONDS` | 1 | 0–60 |
| `GEMINI_RETRY_MAX_DELAY_SECONDS` | 8 | 0–120 |

Retries apply only to HTTP 408, 429, 500, 502, 503, and 504 responses. Raw SDK
errors are converted to sanitized domain exceptions. The client never includes
the API key or provider error body in its own error messages.

Never place a real key in source code, `.env.example`, command-line arguments,
notebooks, fixtures, logs, or screenshots. A key pasted into chat or committed
to source control must be revoked and replaced.
