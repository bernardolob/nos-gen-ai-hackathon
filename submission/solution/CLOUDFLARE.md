# Free Cloudflare gateway

The browser-facing deployment uses this request path:

```text
browser
  -> Cloudflare Worker (validation, CORS, and per-IP rate limit)
  -> Gemini REST API (server-held GEMINI_API_KEY)
```

The Worker runs on Cloudflare's normal Workers Free plan and does not use a
Container or Durable Object. The Python/FastAPI implementation remains useful
for local development and tests, but it is not part of the Cloudflare deploy.

`GEMINI_API_KEY` is never sent to browser code. The Worker accepts generation
requests only from an exact origin listed in `PUBLIC_APP_ORIGINS`, validates
their JSON and size, and calls Gemini with its encrypted secret binding.

The edge exposes only:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Worker liveness; does not call Gemini |
| `OPTIONS` | `/api/v1/generate` | Browser CORS preflight |
| `POST` | `/api/v1/generate` | Rate-limited Gemini generation |

## Configure

From the repository root, install the locked dependencies and log in:

```bash
npm ci
npx wrangler login
```

In `wrangler.jsonc`, replace the development value of
`PUBLIC_APP_ORIGINS` with the exact production frontend origin. Multiple exact
origins may be separated by commas. Do not use `*`.

Create the Gemini secret interactively:

```bash
npx wrangler secret put GEMINI_API_KEY
```

The `API_RATE_LIMITER` binding permits ten generation requests per client IP
per minute. Give its `namespace_id` a distinct positive integer if the
Cloudflare account already uses namespace `1001` for another rate limiter.

## Validate and deploy

```bash
npm run check
npx wrangler deploy --dry-run
npm run deploy
```

## Browser request

The browser sends no API key or bearer token:

```javascript
const response = await fetch(
  "https://nos-gemini-gateway.<workers-subdomain>.workers.dev/api/v1/generate",
  {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  },
);

if (!response.ok) {
  throw new Error(`Generation failed (${response.status})`);
}

const result = await response.json();
```

An origin allowlist and rate limit reduce accidental exposure and basic abuse,
but they are not user authentication. A public production application should
also validate an authenticated user session or a Cloudflare Turnstile token
before forwarding costly requests.

## Privacy and logs

The submitted text passes through the Worker and Gemini. The Worker does not log
request or response bodies and sends `store: false` to Gemini. Keep body logging
disabled in any additional observability or error-reporting integration. Check
Google's current Gemini terms before using free-tier processing for personal or
confidential information.
