interface RateLimiter {
  limit(options: { key: string }): Promise<{ success: boolean }>;
}

interface Env {
  API_RATE_LIMITER: RateLimiter;
  GEMINI_API_KEY: string;
  GEMINI_MODEL: string;
  PUBLIC_APP_ORIGINS: string;
  MAX_PROMPT_LENGTH: string;
  MAX_REQUEST_BYTES: string;
}

interface GenerationPayload {
  prompt: string;
}

interface GeminiResponse {
  candidates?: Array<{
    content?: {
      parts?: Array<{ text?: unknown }>;
    };
  }>;
}

const GENERATE_PATH = "/api/v1/generate";
const HEALTH_PATH = "/health";
const GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta";
const GEMINI_TIMEOUT_MS = 60_000;

function allowedOrigins(env: Env): Set<string> {
  return new Set(
    env.PUBLIC_APP_ORIGINS.split(",")
      .map((origin) => origin.trim().replace(/\/$/, ""))
      .filter(Boolean),
  );
}

function requestOrigin(request: Request): string | null {
  const value = request.headers.get("Origin");
  return value ? value.replace(/\/$/, "") : null;
}

function corsHeaders(origin: string): HeadersInit {
  return {
    "Access-Control-Allow-Headers": "Content-Type, X-Request-ID",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Origin": origin,
    "Access-Control-Expose-Headers": "X-Request-ID",
    "Access-Control-Max-Age": "86400",
    Vary: "Origin",
  };
}

function secureHeaders(requestId: string): HeadersInit {
  return {
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-Request-ID": requestId,
  };
}

function responseHeaders(requestId: string, origin?: string): Headers {
  const headers = new Headers(secureHeaders(requestId));
  if (origin) {
    for (const [name, value] of Object.entries(corsHeaders(origin))) {
      headers.set(name, value);
    }
  }
  return headers;
}

function jsonResponse(
  body: unknown,
  status: number,
  requestId: string,
  origin?: string,
): Response {
  return Response.json(body, {
    status,
    headers: responseHeaders(requestId, origin),
  });
}

function errorResponse(
  detail: string,
  status: number,
  requestId: string,
  origin?: string,
): Response {
  return jsonResponse({ detail }, status, requestId, origin);
}

function positiveInteger(value: string): number | null {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

function modelId(env: Env): string | null {
  const model = env.GEMINI_MODEL.trim().replace(/^models\//, "");
  return /^[A-Za-z0-9._-]+$/.test(model) ? model : null;
}

async function parseGenerationPayload(
  request: Request,
  env: Env,
): Promise<GenerationPayload | null> {
  const maxBytes = positiveInteger(env.MAX_REQUEST_BYTES);
  const maxPromptLength = positiveInteger(env.MAX_PROMPT_LENGTH);
  if (maxBytes === null || maxPromptLength === null) {
    throw new Error("Invalid Worker limits");
  }

  const declaredLength = request.headers.get("Content-Length");
  if (declaredLength && Number(declaredLength) > maxBytes) {
    return null;
  }

  const rawBody = await request.text();
  if (new TextEncoder().encode(rawBody).byteLength > maxBytes) {
    return null;
  }

  let value: unknown;
  try {
    value = JSON.parse(rawBody);
  } catch {
    return null;
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }

  const keys = Object.keys(value);
  const prompt = (value as Record<string, unknown>).prompt;
  if (
    keys.length !== 1 ||
    keys[0] !== "prompt" ||
    typeof prompt !== "string" ||
    !prompt.trim() ||
    prompt.length > maxPromptLength
  ) {
    return null;
  }
  return { prompt };
}

function extractGeminiText(value: GeminiResponse): string | null {
  const parts = value.candidates?.[0]?.content?.parts;
  if (!Array.isArray(parts)) {
    return null;
  }
  const text = parts
    .map((part) => part.text)
    .filter((part): part is string => typeof part === "string")
    .join("");
  return text.trim() ? text : null;
}

async function generateText(
  prompt: string,
  env: Env,
): Promise<{ model: string; text: string }> {
  const model = modelId(env);
  if (!model) {
    throw new Error("Invalid Gemini model configuration");
  }

  const response = await fetch(
    `${GEMINI_API_ROOT}/models/${encodeURIComponent(model)}:generateContent`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "x-goog-api-key": env.GEMINI_API_KEY,
      },
      body: JSON.stringify({
        contents: [{ role: "user", parts: [{ text: prompt }] }],
        store: false,
      }),
      signal: AbortSignal.timeout(GEMINI_TIMEOUT_MS),
    },
  );

  if (!response.ok) {
    await response.body?.cancel();
    const error = new Error("Gemini request failed");
    Object.assign(error, { providerStatus: response.status });
    throw error;
  }

  const value = (await response.json()) as GeminiResponse;
  const text = extractGeminiText(value);
  if (!text) {
    throw new Error("Gemini returned an invalid response");
  }
  return { model, text };
}

function providerStatus(error: unknown): number | null {
  if (typeof error !== "object" || error === null) {
    return null;
  }
  const status = (error as { providerStatus?: unknown }).providerStatus;
  return typeof status === "number" ? status : null;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const requestId = crypto.randomUUID();
    const url = new URL(request.url);

    if (url.pathname === HEALTH_PATH && request.method === "GET") {
      return jsonResponse({ status: "ok" }, 200, requestId);
    }
    if (url.pathname !== GENERATE_PATH) {
      return errorResponse("Not found.", 404, requestId);
    }

    const origin = requestOrigin(request);
    if (!origin || !allowedOrigins(env).has(origin)) {
      return errorResponse("Origin is not allowed.", 403, requestId);
    }
    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: responseHeaders(requestId, origin),
      });
    }
    if (request.method !== "POST") {
      return errorResponse("Method not allowed.", 405, requestId, origin);
    }
    if (
      !request.headers
        .get("Content-Type")
        ?.toLowerCase()
        .startsWith("application/json")
    ) {
      return errorResponse(
        "Content-Type must be application/json.",
        415,
        requestId,
        origin,
      );
    }

    const rateLimitKey = request.headers.get("CF-Connecting-IP") ?? "unknown";
    const { success } = await env.API_RATE_LIMITER.limit({ key: rateLimitKey });
    if (!success) {
      return errorResponse("Too many requests.", 429, requestId, origin);
    }

    let payload: GenerationPayload | null;
    try {
      payload = await parseGenerationPayload(request, env);
    } catch {
      return errorResponse(
        "Worker configuration is invalid.",
        503,
        requestId,
        origin,
      );
    }
    if (!payload) {
      return errorResponse("Request validation failed.", 422, requestId, origin);
    }

    try {
      const result = await generateText(payload.prompt, env);
      return jsonResponse(result, 200, requestId, origin);
    } catch (error) {
      const status = providerStatus(error);
      if (status === 408 || status === 429 || (status !== null && status >= 500)) {
        return errorResponse(
          "Gemini is temporarily unavailable.",
          503,
          requestId,
          origin,
        );
      }
      return errorResponse(
        "Gemini returned an invalid response.",
        502,
        requestId,
        origin,
      );
    }
  },
} satisfies ExportedHandler<Env>;
