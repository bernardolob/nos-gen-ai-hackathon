import detectionSchema from "../submission/solution/detection_schema.json";

interface RateLimiter {
  limit(options: { key: string }): Promise<{ success: boolean }>;
}

interface Env {
  API_RATE_LIMITER: RateLimiter;
  GEMINI_API_KEY: string;
  GEMINI_MODEL: string;
  GEMINI_MEDIA_MODEL: string;
  PUBLIC_APP_ORIGINS: string;
  MAX_PROMPT_LENGTH: string;
  MAX_REQUEST_BYTES: string;
  MAX_MEDIA_REQUEST_BYTES: string;
  MAX_MEDIA_FRAME_BYTES: string;
  MAX_MEDIA_FRAMES: string;
}

/** The answer shapes a client may ask for. The schemas live here, never in the request. */
const RESPONSE_FORMATS = { detection: detectionSchema } as const;
type ResponseFormat = keyof typeof RESPONSE_FORMATS;

interface GenerationPayload {
  prompt: string;
  format?: ResponseFormat;
}

interface MediaFrame {
  frame_id: number;
  mime_type: "image/jpeg";
  data: string;
}

interface MediaPayload {
  prompt: string;
  frames: MediaFrame[];
}

interface GeminiResponse {
  candidates?: Array<{
    content?: { parts?: Array<{ text?: unknown }> };
  }>;
}

interface ProviderDetection {
  frame_id: number;
  box_2d: number[];
  category: string;
  kind: string;
  reason: string;
  confidence: string;
}

const GENERATE_PATH = "/api/v1/generate";
const MEDIA_ANALYZE_PATH = "/api/v1/media/analyze";
const MEDIA_CAPABILITIES_PATH = "/api/v1/media/capabilities";
const HEALTH_PATH = "/health";
const GEMINI_API_ROOT = "https://generativelanguage.googleapis.com/v1beta";
const GEMINI_TIMEOUT_MS = 60_000;
const REQUIRED_MEDIA_CAPABILITIES = [
  "image",
  "video",
  "structured_output",
] as const;
const MEDIA_MODELS = new Set([
  "gemini-3.5-flash-lite",
  "gemini-3.5-flash",
  "gemini-3.6-flash",
  "gemini-3.7-flash",
  "gemini-3.8-flash",
]);
const CATEGORIES = new Set([
  "identificacao",
  "saude",
  "genetico",
  "biometrico",
  "origem_religiao_politica",
  "financeiro",
  "familia",
  "comportamento",
  "quasi_identificador",
]);
const KINDS = new Set([
  "face",
  "text",
  "identity_document",
  "plate",
  "signature",
  "biometric",
  "code",
  "other",
]);
const CONFIDENCE = new Set(["certo", "provavel", "incerto"]);

const MEDIA_RESPONSE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  required: ["detections"],
  properties: {
    detections: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        required: [
          "frame_id",
          "box_2d",
          "category",
          "kind",
          "reason",
          "confidence",
        ],
        properties: {
          frame_id: { type: "integer", minimum: 0 },
          box_2d: {
            type: "array",
            minItems: 4,
            maxItems: 4,
            items: { type: "integer", minimum: 0, maximum: 1000 },
          },
          category: { type: "string", enum: [...CATEGORIES] },
          kind: { type: "string", enum: [...KINDS] },
          reason: { type: "string", minLength: 1, maxLength: 240 },
          confidence: { type: "string", enum: [...CONFIDENCE] },
        },
      },
    },
  },
};

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
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
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

function configuredModel(value: string): string | null {
  const model = value.trim().replace(/^models\//, "");
  return /^[A-Za-z0-9._-]+$/.test(model) ? model : null;
}

function textModelId(env: Env): string | null {
  return configuredModel(env.GEMINI_MODEL);
}

function mediaModelId(env: Env): string | null {
  const model = configuredModel(env.GEMINI_MEDIA_MODEL);
  return model && MEDIA_MODELS.has(model) ? model : null;
}

async function readJsonBody(
  request: Request,
  maxBytes: number,
): Promise<unknown | null> {
  const declaredLength = request.headers.get("Content-Length");
  if (declaredLength && Number(declaredLength) > maxBytes) {
    return null;
  }
  const rawBody = await request.text();
  if (new TextEncoder().encode(rawBody).byteLength > maxBytes) {
    return null;
  }
  try {
    return JSON.parse(rawBody);
  } catch {
    return null;
  }
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
  const value = await readJsonBody(request, maxBytes);
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  const keys = Object.keys(value);
  const prompt = (value as Record<string, unknown>).prompt;
  const format = (value as Record<string, unknown>).format;
  if (
    !keys.includes("prompt") ||
    keys.some((key) => key !== "prompt" && key !== "format") ||
    typeof prompt !== "string" ||
    !prompt.trim() ||
    prompt.length > maxPromptLength
  ) {
    return null;
  }
  if (keys.includes("format")) {
    if (
      typeof format !== "string" ||
      !Object.prototype.hasOwnProperty.call(RESPONSE_FORMATS, format)
    ) {
      return null;
    }
    return { prompt, format: format as ResponseFormat };
  }
  return { prompt };
}

function validBase64Jpeg(data: string, maxBytes: number): boolean {
  if (!data || data.length > Math.ceil(maxBytes / 3) * 4 + 4) {
    return false;
  }
  if (!/^[A-Za-z0-9+/]+={0,2}$/.test(data)) {
    return false;
  }
  try {
    const decoded = atob(data);
    return (
      decoded.length <= maxBytes &&
      decoded.length >= 3 &&
      decoded.charCodeAt(0) === 0xff &&
      decoded.charCodeAt(1) === 0xd8 &&
      decoded.charCodeAt(2) === 0xff
    );
  } catch {
    return false;
  }
}

async function parseMediaPayload(
  request: Request,
  env: Env,
): Promise<MediaPayload | null> {
  const maxBytes = positiveInteger(env.MAX_MEDIA_REQUEST_BYTES);
  const maxFrameBytes = positiveInteger(env.MAX_MEDIA_FRAME_BYTES);
  const maxFrames = positiveInteger(env.MAX_MEDIA_FRAMES);
  const maxPromptLength = positiveInteger(env.MAX_PROMPT_LENGTH);
  if (
    maxBytes === null ||
    maxFrameBytes === null ||
    maxFrames === null ||
    maxPromptLength === null
  ) {
    throw new Error("Invalid Worker limits");
  }
  const value = await readJsonBody(request, maxBytes);
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  const record = value as Record<string, unknown>;
  if (
    Object.keys(record).length !== 2 ||
    typeof record.prompt !== "string" ||
    !record.prompt.trim() ||
    record.prompt.length > maxPromptLength ||
    !Array.isArray(record.frames) ||
    record.frames.length < 1 ||
    record.frames.length > maxFrames
  ) {
    return null;
  }
  const frames: MediaFrame[] = [];
  const ids = new Set<number>();
  for (const item of record.frames) {
    if (typeof item !== "object" || item === null || Array.isArray(item)) {
      return null;
    }
    const frame = item as Record<string, unknown>;
    if (
      Object.keys(frame).length !== 3 ||
      !Number.isSafeInteger(frame.frame_id) ||
      (frame.frame_id as number) < 0 ||
      ids.has(frame.frame_id as number) ||
      frame.mime_type !== "image/jpeg" ||
      typeof frame.data !== "string" ||
      !validBase64Jpeg(frame.data, maxFrameBytes)
    ) {
      return null;
    }
    ids.add(frame.frame_id as number);
    frames.push(frame as unknown as MediaFrame);
  }
  return { prompt: record.prompt, frames };
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

async function callGemini(
  model: string,
  body: unknown,
  env: Env,
): Promise<GeminiResponse> {
  const response = await fetch(
    `${GEMINI_API_ROOT}/models/${encodeURIComponent(model)}:generateContent`,
    {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "x-goog-api-key": env.GEMINI_API_KEY,
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(GEMINI_TIMEOUT_MS),
    },
  );
  if (!response.ok) {
    await response.body?.cancel();
    const error = new Error("Gemini request failed");
    Object.assign(error, { providerStatus: response.status });
    throw error;
  }
  return (await response.json()) as GeminiResponse;
}

async function generateText(
  prompt: string,
  env: Env,
  format?: ResponseFormat,
): Promise<{ model: string; text: string }> {
  const model = textModelId(env);
  if (!model) {
    throw new Error("Invalid Gemini model configuration");
  }
  const value = await callGemini(
    model,
    {
      contents: [{ role: "user", parts: [{ text: prompt }] }],
      ...(format
        ? {
            generationConfig: {
              responseMimeType: "application/json",
              responseSchema: RESPONSE_FORMATS[format],
            },
          }
        : {}),
      store: false,
    },
    env,
  );
  const text = extractGeminiText(value);
  if (!text) {
    throw new Error("Gemini returned an invalid response");
  }
  return { model, text };
}

function validDetection(value: unknown, frameIds: Set<number>): boolean {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const item = value as Record<string, unknown>;
  if (
    Object.keys(item).length !== 6 ||
    !Number.isSafeInteger(item.frame_id) ||
    !frameIds.has(item.frame_id as number) ||
    !Array.isArray(item.box_2d) ||
    item.box_2d.length !== 4 ||
    !item.box_2d.every(
      (coordinate) =>
        Number.isInteger(coordinate) &&
        (coordinate as number) >= 0 &&
        (coordinate as number) <= 1000,
    ) ||
    (item.box_2d[0] as number) >= (item.box_2d[2] as number) ||
    (item.box_2d[1] as number) >= (item.box_2d[3] as number) ||
    typeof item.category !== "string" ||
    !CATEGORIES.has(item.category) ||
    typeof item.kind !== "string" ||
    !KINDS.has(item.kind) ||
    typeof item.reason !== "string" ||
    !item.reason.trim() ||
    item.reason.length > 240 ||
    typeof item.confidence !== "string" ||
    !CONFIDENCE.has(item.confidence)
  ) {
    return false;
  }
  return true;
}

async function analyzeMedia(
  payload: MediaPayload,
  env: Env,
): Promise<{ detections: ProviderDetection[] }> {
  const model = mediaModelId(env);
  if (!model) {
    throw new Error("Invalid Gemini media model configuration");
  }
  const parts: Array<Record<string, unknown>> = [{ text: payload.prompt }];
  for (const frame of payload.frames) {
    parts.push({ text: `frame_id=${frame.frame_id}` });
    parts.push({
      inlineData: { mimeType: frame.mime_type, data: frame.data },
    });
  }
  const value = await callGemini(
    model,
    {
      contents: [{ role: "user", parts }],
      generationConfig: {
        temperature: 0,
        responseMimeType: "application/json",
        responseJsonSchema: MEDIA_RESPONSE_SCHEMA,
      },
      store: false,
    },
    env,
  );
  const text = extractGeminiText(value);
  let parsed: unknown;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = null;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("Gemini returned invalid media JSON");
  }
  const result = parsed as Record<string, unknown>;
  const frameIds = new Set(payload.frames.map((frame) => frame.frame_id));
  if (
    Object.keys(result).length !== 1 ||
    !Array.isArray(result.detections) ||
    !result.detections.every((item) => validDetection(item, frameIds))
  ) {
    throw new Error("Gemini returned invalid media JSON");
  }
  return { detections: result.detections as ProviderDetection[] };
}

async function verifyMediaModel(env: Env) {
  const model = mediaModelId(env);
  if (!model) {
    throw new Error("Invalid Gemini media model configuration");
  }
  const response = await fetch(
    `${GEMINI_API_ROOT}/models/${encodeURIComponent(model)}`,
    {
      headers: {
        Accept: "application/json",
        "x-goog-api-key": env.GEMINI_API_KEY,
      },
      signal: AbortSignal.timeout(GEMINI_TIMEOUT_MS),
    },
  );
  if (!response.ok) {
    await response.body?.cancel();
    const error = new Error("Gemini media model verification failed");
    Object.assign(error, { providerStatus: response.status });
    throw error;
  }
  const value = (await response.json()) as {
    name?: unknown;
    supportedGenerationMethods?: unknown;
  };
  const methods = value.supportedGenerationMethods;
  if (
    value.name !== `models/${model}` ||
    !Array.isArray(methods) ||
    !methods.includes("generateContent")
  ) {
    throw new Error("Gemini media model identity could not be verified");
  }
  return {
    model: {
      id: model,
      capabilities: [...REQUIRED_MEDIA_CAPABILITIES],
      verified: true,
    },
  };
}

function providerStatus(error: unknown): number | null {
  if (typeof error !== "object" || error === null) {
    return null;
  }
  const status = (error as { providerStatus?: unknown }).providerStatus;
  return typeof status === "number" ? status : null;
}

function isTemporaryProviderError(error: unknown): boolean {
  const status = providerStatus(error);
  return status === 408 || status === 429 || (status !== null && status >= 500);
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const requestId = crypto.randomUUID();
    const url = new URL(request.url);

    if (url.pathname === HEALTH_PATH && request.method === "GET") {
      return jsonResponse({ status: "ok" }, 200, requestId);
    }
    const apiPaths = new Set([
      GENERATE_PATH,
      MEDIA_ANALYZE_PATH,
      MEDIA_CAPABILITIES_PATH,
    ]);
    if (!apiPaths.has(url.pathname)) {
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
    const expectedMethod =
      url.pathname === MEDIA_CAPABILITIES_PATH ? "GET" : "POST";
    if (request.method !== expectedMethod) {
      return errorResponse("Method not allowed.", 405, requestId, origin);
    }
    if (
      request.method === "POST" &&
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

    if (url.pathname === MEDIA_CAPABILITIES_PATH) {
      try {
        return jsonResponse(await verifyMediaModel(env), 200, requestId, origin);
      } catch {
        return errorResponse(
          "Media model is not configured or does not support image/video.",
          503,
          requestId,
          origin,
        );
      }
    }

    if (url.pathname === GENERATE_PATH) {
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
        return errorResponse(
          "Request validation failed.",
          422,
          requestId,
          origin,
        );
      }
      try {
        return jsonResponse(
          await generateText(payload.prompt, env, payload.format),
          200,
          requestId,
          origin,
        );
      } catch (error) {
        return errorResponse(
          isTemporaryProviderError(error)
            ? "Gemini is temporarily unavailable."
            : "Gemini returned an invalid response.",
          isTemporaryProviderError(error) ? 503 : 502,
          requestId,
          origin,
        );
      }
    }

    let mediaPayload: MediaPayload | null;
    try {
      mediaPayload = await parseMediaPayload(request, env);
    } catch {
      return errorResponse(
        "Worker configuration is invalid.",
        503,
        requestId,
        origin,
      );
    }
    if (!mediaPayload) {
      return errorResponse(
        "Media request validation failed.",
        422,
        requestId,
        origin,
      );
    }
    try {
      return jsonResponse(
        await analyzeMedia(mediaPayload, env),
        200,
        requestId,
        origin,
      );
    } catch (error) {
      return errorResponse(
        isTemporaryProviderError(error)
          ? "Gemini is temporarily unavailable."
          : "Gemini returned an invalid media response.",
        isTemporaryProviderError(error) ? 503 : 502,
        requestId,
        origin,
      );
    }
  },
} satisfies ExportedHandler<Env>;
