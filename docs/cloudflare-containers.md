# Cloudflare Containers deployment

This repository prepares, but does not perform, a Cloudflare deployment. The
architecture is:

```text
browser or private client
        -> Cloudflare Worker
        -> FastAPI Cloudflare Container
        -> gemini-3.5-flash
        -> FastAPI -> Worker -> client
```

Review Cloudflare's current [Containers overview](https://developers.cloudflare.com/containers/),
[pricing](https://developers.cloudflare.com/containers/platform/pricing/), and
[limits](https://developers.cloudflare.com/containers/platform/limits/) before
deploying.

## Routing

`wrangler.jsonc` binds `BACKEND` to the `BackendContainer` Durable Object class
in `cloudflare/worker.ts`. The Worker selects one stable instance name
(`api-v1`). The Durable Object starts the Docker image, passes runtime settings,
waits for `/health`, and forwards the original request to FastAPI on port 8080.
Outbound internet access is enabled only because the container must reach
Gemini. The application does not use the ephemeral filesystem for data.

## Configure and deploy

Cloudflare Containers require the Workers Paid plan and a working local Docker
engine. Install the locked Worker dependencies and authenticate Wrangler:

```bash
npm ci
npx wrangler login
```

Set `BACKEND_CORS_ALLOW_ORIGINS` under `vars` in `wrangler.jsonc` to the exact
frontend origin, such as `https://app.example.com`. Leave it empty if no browser
origin should be permitted. Wildcards are rejected by FastAPI.

Create both secrets interactively:

```bash
npx wrangler secret put GEMINI_API_KEY
npx wrangler secret put BACKEND_API_TOKEN
```

Use a newly generated Gemini key. Secret names are declared for validation, but
secret values must never appear in `wrangler.jsonc`, `wrangler.toml`, source
files, the Dockerfile, shell history, logs, or frontend JavaScript. Wrangler
stores the values as encrypted Worker secrets and the Worker passes them to the
container only as runtime environment variables.

Validate and deploy:

```bash
npm run check
npx wrangler deploy
npx wrangler containers list
```

Wrangler builds a `linux/amd64` image, uploads the Worker and image, and
provisions the Container application. No deployment is performed by this
repository setup.

## Verify

`/health` confirms only that FastAPI is running. `/ready` is protected and calls
`GeminiClient.check_connection()`:

```bash
curl https://nos-gemini-gateway.<workers-subdomain>.workers.dev/health
curl -H "Authorization: Bearer $BACKEND_API_TOKEN" \
  https://nos-gemini-gateway.<workers-subdomain>.workers.dev/ready
```

For a private generation test:

```bash
curl -X POST \
  -H "Authorization: Bearer $BACKEND_API_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"prompt":"say hi"}' \
  https://nos-gemini-gateway.<workers-subdomain>.workers.dev/api/v1/generate
```

Do not put the bearer token in public browser JavaScript. Before public access,
replace this private-test mechanism with user sessions, Cloudflare Access, or
Turnstile plus rate limiting.

## Operational limits

- Containers are unavailable on the free plan; the Workers Paid plan includes
  a usage allowance and bills additional Worker, Durable Object, compute,
  storage, and network usage.
- Containers can sleep after inactivity. The first request then waits for a
  cold start, and first deployment provisioning may take several minutes.
- This private-test configuration uses one named `lite` instance. It is not a
  production autoscaling or high-availability design.
- The image must support `linux/amd64`; the `lite` instance has finite CPU,
  memory, and ephemeral disk.
- Cloudflare edge request limits still apply independently of the smaller
  application limit.
- Secret updates reach a container the next time that container starts; restart
  an already-running instance when rotating credentials.

## Roll back

List deployments, then roll back to the preceding or a specified version:

```bash
npx wrangler deployments list
npx wrangler rollback
# or: npx wrangler rollback <VERSION_ID>
```

The dashboard path is **Workers & Pages -> your Worker -> Deployments**. A
rollback immediately makes the selected version active, but does not restore
deleted or changed external resources. Recheck `/health` and `/ready` after a
rollback.
