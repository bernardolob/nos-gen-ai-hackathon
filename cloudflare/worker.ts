import { DurableObject } from "cloudflare:workers";

interface Env {
  BACKEND: DurableObjectNamespace<BackendContainer>;
  GEMINI_API_KEY: string;
  BACKEND_API_TOKEN: string;
  BACKEND_HOST: string;
  BACKEND_PORT: string;
  BACKEND_WORKERS: string;
  BACKEND_PRODUCTION: string;
  BACKEND_CORS_ALLOW_ORIGINS: string;
  BACKEND_MAX_BLOCK_COUNT: string;
  BACKEND_MAX_TEXT_LENGTH: string;
  BACKEND_MAX_REQUEST_BYTES: string;
}

const INACTIVITY_TIMEOUT_MS = 10 * 60 * 1000;
const START_ATTEMPTS = 100;

export class BackendContainer extends DurableObject<Env> {
  private starting: Promise<void> | undefined;

  constructor(ctx: DurableObjectState, env: Env) {
    super(ctx, env);
    const container = ctx.container!;
    if (container.running) {
      void ctx.blockConcurrencyWhile(() =>
        container.setInactivityTimeout(INACTIVITY_TIMEOUT_MS),
      );
    }
  }

  async fetch(request: Request): Promise<Response> {
    this.starting ??= this.startAndWaitForHealth().finally(() => {
      this.starting = undefined;
    });
    await this.starting;

    const url = new URL(request.url);
    url.protocol = "http:";
    url.host = "container";
    const forwarded = new Request(url, request);
    forwarded.headers.delete("host");
    return this.ctx.container!
      .getTcpPort(this.containerPort())
      .fetch(forwarded);
  }

  private containerPort(): number {
    const port = Number(this.env.BACKEND_PORT);
    if (!Number.isInteger(port) || port < 1 || port > 65535) {
      throw new Error("BACKEND_PORT is invalid");
    }
    return port;
  }

  private async startAndWaitForHealth(): Promise<void> {
    const container = this.ctx.container!;
    const portNumber = this.containerPort();
    if (!container.running) {
      container.start({
        image: container.images.api,
        instance: "lite",
        enableInternet: true,
        env: {
          GEMINI_API_KEY: this.env.GEMINI_API_KEY,
          BACKEND_API_TOKEN: this.env.BACKEND_API_TOKEN,
          BACKEND_HOST: this.env.BACKEND_HOST,
          BACKEND_PORT: this.env.BACKEND_PORT,
          BACKEND_WORKERS: this.env.BACKEND_WORKERS,
          BACKEND_PRODUCTION: this.env.BACKEND_PRODUCTION,
          BACKEND_CORS_ALLOW_ORIGINS: this.env.BACKEND_CORS_ALLOW_ORIGINS,
          BACKEND_MAX_BLOCK_COUNT: this.env.BACKEND_MAX_BLOCK_COUNT,
          BACKEND_MAX_TEXT_LENGTH: this.env.BACKEND_MAX_TEXT_LENGTH,
          BACKEND_MAX_REQUEST_BYTES: this.env.BACKEND_MAX_REQUEST_BYTES,
        },
      });
    }
    await container.setInactivityTimeout(INACTIVITY_TIMEOUT_MS);

    const port = container.getTcpPort(portNumber);
    for (let attempt = 0; attempt < START_ATTEMPTS; attempt += 1) {
      try {
        const response = await port.fetch("http://container/health", {
          signal: AbortSignal.timeout(1000),
        });
        await response.body?.cancel();
        if (response.ok) {
          return;
        }
      } catch {
        // A subsequent bounded attempt handles normal cold-start races.
      }
      await scheduler.wait(200);
    }
    throw new Error("Backend container did not become healthy");
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    try {
      return await env.BACKEND.getByName("api-v1").fetch(request);
    } catch {
      return Response.json(
        { detail: "Backend container is unavailable." },
        { status: 503 },
      );
    }
  },
} satisfies ExportedHandler<Env>;
