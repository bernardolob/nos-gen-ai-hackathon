# Cloudflare Containers deployment

This repository prepares, but does not perform, a Cloudflare Containers
deployment. Cloudflare Containers require the Workers Paid plan. Review the
current [Containers overview](https://developers.cloudflare.com/containers/),
[pricing](https://developers.cloudflare.com/containers/platform/pricing/), and
[limits](https://developers.cloudflare.com/containers/platform/limits/) before
deploying.

## Request routing

`wrangler.toml` binds the `BACKEND` Durable Object namespace to the
`BackendContainer` class in `cloudflare/worker.ts`. The Worker selects one
stable instance name (`api-v1`). The Durable Object starts the Docker image,
passes its runtime settings, waits for `/health`, and proxies the original HTTP
request to FastAPI on the configured port. Container internet access is enabled
only because FastAPI must call Gemini. The ephemeral container filesystem is
not used for application data.

The fixed instance is intentionally simple for private testing; it is not
built-in stateless autoscaling. Cloudflare currently requires applications to
address instances explicitly. Revisit routing and capacity before public use.

## Configure and deploy

Install the checked-in Worker dependencies and authenticate Wrangler:

```bash
npm ci
npx wrangler login
```

Edit only non-secret values under `[vars]` in `wrangler.toml`, especially
`BACKEND_CORS_ALLOW_ORIGINS`. It must be a comma-separated list of exact
frontend origins such as `https://app.example.com`; wildcard CORS is rejected.

Create secrets interactively so their values are stored by Cloudflare, not in
shell history or source control:

```bash
npx wrangler secret put GEMINI_API_KEY
npx wrangler secret put BACKEND_API_TOKEN
```

Use a newly generated Gemini key. Never place either secret in
`wrangler.toml`, `.env`, the Dockerfile, source, or frontend code. Then validate
and deploy:

```bash
npm run check
npx wrangler deploy
npx wrangler containers list
```

Wrangler builds the `linux/amd64` Docker image, uploads the Worker and image,
and prepares the Container application. The first deployment can take several
minutes to provision even after the Worker URL is available.

## Verify

`/health` is public and confirms only that FastAPI is running. `/ready` is
protected and performs the Gemini connection check:

```bash
curl https://nos-anonymizer-api.<workers-subdomain>.workers.dev/health
curl -H "Authorization: Bearer $BACKEND_API_TOKEN" \
  https://nos-anonymizer-api.<workers-subdomain>.workers.dev/ready
```

Do not put the bearer token in browser JavaScript. Before exposing this to a
public browser client, replace this private-test mechanism with real user
sessions, Cloudflare Access, or Turnstile plus rate limiting.

## Operational constraints

- Containers are available on the Workers Paid plan and usage beyond included
  allowances is billed.
- Instances scale to zero and cold starts commonly take seconds; image size and
  application startup affect latency. The Worker waits for `/health`, but an
  initial deployment can still be unavailable while capacity is provisioned.
- The configured `lite` instance has finite CPU, memory, and ephemeral disk.
  Containers have no swap. Account concurrency and image-storage limits also
  apply.
- The image must support `linux/amd64`. Request-body limits at the Cloudflare
  edge also depend on the account plan, independently of the smaller API limit.
- Built-in autoscaling for interchangeable stateless instances is not currently
  available. This configuration has one named instance and no persistent file
  storage.
- A Worker deploy becomes active before all container image rollout work is
  complete, so Worker and image changes should remain mutually compatible.

## Roll back

List recent deployments and roll back the Worker with Wrangler:

```bash
npx wrangler deployments list
npx wrangler rollback
```

The dashboard also supports rollback under **Workers & Pages → the Worker →
Deployments**. A Worker rollback does not restore changed external resources.
Keep old container images: deleting an image can make a rollback that references
it fail. After rollback, recheck both `/health` and `/ready`.
