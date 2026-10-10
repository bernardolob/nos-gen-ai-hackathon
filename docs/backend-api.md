# Backend API

The FastAPI service is a text-only HTTP gateway around the existing
`GeminiClient`. It does not upload or extract PDFs, perform OCR, store files,
mask content, anonymize documents, run n8n workflows, or create submissions.

The service always uses exactly `gemini-3.5-flash`; there is no fallback. It
reads the Gemini key only from `GEMINI_API_KEY`. The key is never accepted in an
HTTP request or returned to a client.

## Local setup

Install the package and test tools:

```bash
python -m pip install -e ".[test]"
```

Set fresh secrets in the process environment. Never use a key pasted into chat,
put either secret in source, or pass them as command-line values.

```bash
export GEMINI_API_KEY="newly-generated-key"
export BACKEND_API_TOKEN="high-entropy-private-test-token"
export BACKEND_CORS_ALLOW_ORIGINS="http://localhost:3000"
nos-anonymizer-api
```

PowerShell:

```powershell
$env:GEMINI_API_KEY = "newly-generated-key"
$env:BACKEND_API_TOKEN = "high-entropy-private-test-token"
$env:BACKEND_CORS_ALLOW_ORIGINS = "http://localhost:3000"
nos-anonymizer-api
```

The equivalent direct Uvicorn command is:

```bash
uvicorn nos_anonymizer.api:app --host 0.0.0.0 --port 8080 --workers 1 \
  --no-access-log --no-server-header
```

`/health` is public and never contacts Gemini. `/ready` and
`/api/v1/generate` require `Authorization: Bearer <BACKEND_API_TOKEN>`.

```bash
curl http://localhost:8080/health
curl -H "Authorization: Bearer $BACKEND_API_TOKEN" \
  http://localhost:8080/ready
curl -X POST http://localhost:8080/api/v1/generate \
  -H "Authorization: Bearer $BACKEND_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"prompt":"say hi"}'
```

The generation response is validated and contains only the pinned model name
and answer:

```json
{
  "model": "gemini-3.5-flash",
  "text": "Hi there!"
}
```

The bearer token is suitable only for private testing and trusted
server-to-server callers. Never embed `BACKEND_API_TOKEN` in frontend
JavaScript. A public browser application should use real user sessions,
Cloudflare Access, or Turnstile plus rate limiting.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | required | Fresh Gemini credential |
| `BACKEND_API_TOKEN` | required for protected access | Private bearer token |
| `BACKEND_HOST` | `0.0.0.0` | Listen address |
| `BACKEND_PORT` | `8080` | Listen port |
| `BACKEND_WORKERS` | `1` | Uvicorn worker processes |
| `BACKEND_PRODUCTION` | `false` | Disables public API docs when true |
| `BACKEND_CORS_ALLOW_ORIGINS` | empty | Comma-separated exact HTTP(S) origins |
| `BACKEND_MAX_PROMPT_LENGTH` | `10000` | Maximum prompt characters |
| `BACKEND_MAX_REQUEST_BYTES` | `1048576` | Maximum generation body bytes |

Wildcard CORS is rejected. Gemini timeout and retry settings remain documented
in [gemini-integration.md](gemini-integration.md). The service disables Uvicorn
access logs and never logs request bodies, prompts, provider response bodies,
or credentials. Provider errors are returned as fixed sanitized messages.

## Docker

Build the production image:

```bash
docker build -t nos-gemini-gateway:local .
```

Run it without baking secrets into the image:

```bash
docker run --rm -p 8080:8080 \
  -e GEMINI_API_KEY \
  -e BACKEND_API_TOKEN \
  -e BACKEND_CORS_ALLOW_ORIGINS=http://localhost:3000 \
  nos-gemini-gateway:local
```

The image uses a supported slim Python base, runs as a non-root user, and checks
the public `/health` endpoint.
