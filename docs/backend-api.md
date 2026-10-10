# Backend API

The FastAPI service is a text-only HTTP boundary around the existing
`GeminiClient`. It does not upload or extract PDFs, perform OCR, store files,
mask content, run n8n workflows, or generate a final submission.

The service continues to use exactly `gemini-3.5-flash`; there is no model
fallback. It reads a newly generated Gemini key only from `GEMINI_API_KEY`.
The key is never accepted in a request or returned to a client.

## Local setup

Install the package and test tools:

```bash
python -m pip install -e ".[test]"
```

Set fresh secrets in the process environment. Do not use a key that was pasted
into chat, place either secret in a file, or pass them as command-line values.

```bash
export GEMINI_API_KEY="newly-generated-key"
export BACKEND_API_TOKEN="high-entropy-private-test-token"
export BACKEND_CORS_ALLOW_ORIGINS="http://localhost:3000"
uvicorn nos_anonymizer.api:app --host 0.0.0.0 --port 8080 --workers 1 \
  --no-access-log --no-server-header
```

PowerShell:

```powershell
$env:GEMINI_API_KEY = "newly-generated-key"
$env:BACKEND_API_TOKEN = "high-entropy-private-test-token"
$env:BACKEND_CORS_ALLOW_ORIGINS = "http://localhost:3000"
nos-anonymizer-api
```

`/health` is public and never calls Gemini. `/ready` and `/api/v1/detect`
require `Authorization: Bearer <BACKEND_API_TOKEN>`.

```bash
curl http://localhost:8080/health
curl -H "Authorization: Bearer $BACKEND_API_TOKEN" \
  http://localhost:8080/ready
curl -X POST http://localhost:8080/api/v1/detect \
  -H "Authorization: Bearer $BACKEND_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"blocks":[{"block_id":"paragraph-1","text":"Contact Maria at maria@example.com."}]}'
```

The bearer token is appropriate only for private testing and trusted
server-to-server callers. Never embed `BACKEND_API_TOKEN` in frontend
JavaScript: a public browser application must instead use real user sessions,
Cloudflare Access, or Turnstile plus rate limiting.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | required for readiness | Fresh Gemini credential |
| `BACKEND_API_TOKEN` | required for protected access | Private bearer token |
| `BACKEND_HOST` | `0.0.0.0` | Listen address |
| `BACKEND_PORT` | `8080` | Listen port |
| `BACKEND_WORKERS` | `1` | Uvicorn worker processes |
| `BACKEND_PRODUCTION` | `false` | Disables `/docs`, `/redoc`, and OpenAPI when true |
| `BACKEND_CORS_ALLOW_ORIGINS` | empty | Comma-separated exact HTTP(S) origins; `*` is rejected |
| `BACKEND_MAX_BLOCK_COUNT` | `100` | Maximum blocks per detection request |
| `BACKEND_MAX_TEXT_LENGTH` | `10000` | Maximum Unicode characters in one block |
| `BACKEND_MAX_REQUEST_BYTES` | `1048576` | Maximum detection request body bytes |

Gemini timeout and retry variables remain documented in
[gemini-integration.md](gemini-integration.md). The service logs request IDs,
not request bodies, submitted text, provider response bodies, or credentials.
Provider failures are mapped to sanitized responses. Gemini credential errors
are upstream readiness failures (`503`), never caller authentication errors.

## Docker

Build the production image:

```bash
docker build -t nos-anonymizer-api:local .
```

Run it without baking secrets into the image:

```bash
docker run --rm -p 8080:8080 \
  -e GEMINI_API_KEY \
  -e BACKEND_API_TOKEN \
  -e BACKEND_CORS_ALLOW_ORIGINS=http://localhost:3000 \
  nos-anonymizer-api:local
```

The image uses a supported slim Python base, runs as a non-root user, disables
Uvicorn access logging, and checks the public `/health` endpoint.
