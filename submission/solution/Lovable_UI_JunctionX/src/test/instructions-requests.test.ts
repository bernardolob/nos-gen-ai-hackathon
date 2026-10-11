import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MAX_INSTRUCTIONS } from "@/lib/review/types";

/**
 * The upload functions in live mode (not the demo): the fetch is faked, so we
 * see exactly what would leave the browser. `isMockMode` is read when the
 * module loads, hence the stubbed env and the fresh import.
 */
const SNAPSHOT = { has_document: true, status: "ready" };
const TEXT = "Mascara também a ação.\nNão mascares a clínica.";

type Call = { url: string; headers: Record<string, string>; body: unknown };

async function liveApi() {
  vi.resetModules();
  vi.stubEnv("MODE", "development");
  vi.stubEnv("VITE_API_URL", "http://127.0.0.1:8000");
  vi.stubEnv("VITE_USE_MOCK", "false");
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, headers: { ...(init.headers as Record<string, string>) }, body: init.body });
      return new Response(JSON.stringify(SNAPSHOT), { status: 200 });
    }),
  );
  const api = await import("@/lib/review/api");
  expect(api.isMockMode).toBe(false);
  return { api, calls };
}

const textFile = () => new File(["Nome: Ana"], "nota.txt", { type: "text/plain" });
const audioFile = () => new File(["audio"], "voz.mp3", { type: "audio/mpeg" });
const imageFile = () => new File(["img"], "foto de Ana.png", { type: "image/png" });
const videoFile = () => new File(["vid"], "clip.mp4", { type: "video/mp4" });

describe("instructions in the real upload requests", () => {
  beforeEach(() => vi.unstubAllGlobals());
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it.each([
    ["a document", textFile, "/api/document"],
    ["an audio file", audioFile, "/api/audio"],
    ["an image", imageFile, "/api/document"],
    ["a video", videoFile, "/api/document"],
  ])("sends the instructions with %s", async (_name, make, path) => {
    const { api, calls } = await liveApi();
    await api.uploadFile(make(), TEXT);

    expect(calls).toHaveLength(1);
    expect(calls[0]!.url).toBe(`http://127.0.0.1:8000${path}`);
    const header = calls[0]!.headers["X-User-Instructions"];
    expect(header).toBeDefined();
    expect(decodeURIComponent(header as string)).toBe(TEXT);
    expect(header).not.toMatch(/[^\x20-\x7e]/);
  });

  it.each([
    ["a document", textFile],
    ["an audio file", audioFile],
    ["an image", imageFile],
    ["a video", videoFile],
  ])("sends no header for %s when the field is empty", async (_name, make) => {
    const { api, calls } = await liveApi();
    await api.uploadFile(make());
    await api.uploadFile(make(), "   ");

    expect(calls).toHaveLength(2);
    for (const call of calls) expect(call.headers).not.toHaveProperty("X-User-Instructions");
  });

  it("keeps the file name header for media next to the instructions", async () => {
    const { api, calls } = await liveApi();
    await api.uploadFile(imageFile(), "Tapa as caras.");

    const { headers } = calls[0]!;
    expect(decodeURIComponent(headers["X-File-Name"] as string)).toBe("foto de Ana.png");
    expect(headers["Content-Type"]).toBe("image/png");
    expect(decodeURIComponent(headers["X-User-Instructions"] as string)).toBe("Tapa as caras.");
  });

  it("sends the file itself as the body, never the instructions", async () => {
    const { api, calls } = await liveApi();
    const file = textFile();
    await api.uploadFile(file, "Segredo do utilizador");

    expect(calls[0]!.body).toBe(file);
  });

  it("refuses too long instructions before anything is sent", async () => {
    const { api, calls } = await liveApi();

    await expect(api.uploadFile(textFile(), "a".repeat(MAX_INSTRUCTIONS + 1))).rejects.toMatchObject({
      status: 422,
    });
    expect(calls).toHaveLength(0);
  });

  it("sends exactly the longest allowed text", async () => {
    const { api, calls } = await liveApi();
    await api.uploadFile(textFile(), "ç".repeat(MAX_INSTRUCTIONS));

    const header = calls[0]!.headers["X-User-Instructions"] as string;
    expect(decodeURIComponent(header)).toHaveLength(MAX_INSTRUCTIONS);
  });

  it("does not put the instructions in the URL", async () => {
    const { api, calls } = await liveApi();
    await api.uploadFile(textFile(), "Nome da Maria");

    expect(calls[0]!.url).not.toContain("Maria");
    expect(calls[0]!.url).not.toContain("?");
  });
});
