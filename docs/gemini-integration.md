# Gemini connection integration

This milestone does one thing: it creates a secure Python connection to Google
Gemini and verifies access to exactly `gemini-3.5-flash`.

It only retrieves model metadata. It does not generate content, inspect input
text, read files, process PDFs, perform OCR, store data, or redact documents.

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
