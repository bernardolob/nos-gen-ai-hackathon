import { mockApprove, mockCurrent, mockReject, mockUpload, SAMPLE_TEXT } from "./mock";
import { ApiError, MAX_UPLOAD_BYTES, type Snapshot } from "./types";

/** Local backend address used during development (set VITE_API_URL to it to go live). */
export const DEFAULT_API_URL = "http://127.0.0.1:8000";

const RAW = (import.meta.env["VITE_API_URL"] as string | undefined)?.trim();
const API_URL = RAW?.replace(/\/+$/, "");
/** Mock mode when VITE_API_URL is unset or VITE_USE_MOCK=true, so the preview keeps working. */
export const isMockMode = !API_URL || import.meta.env["VITE_USE_MOCK"] === "true";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function contentTypeFor(file: File): "application/pdf" | "text/plain" | null {
  const name = file.name.toLowerCase();
  if (file.type === "application/pdf" || name.endsWith(".pdf")) return "application/pdf";
  if (file.type.startsWith("text/") || name.endsWith(".txt") || name.endsWith(".md")) return "text/plain";
  return null;
}

export async function parseError(res: Response): Promise<ApiError> {
  let detail = "";
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    /* body is not JSON */
  }
  const fallback: Record<number, string> = {
    409: "The version under review has changed. Refresh and try again.",
    413: "The document is larger than 10 MB.",
    415: "Unsupported format. Use PDF or text.",
    422: "The document or the feedback could not be read.",
    502: "The model did not respond. The current version is unchanged; try again.",
  };
  return new ApiError(res.status, detail || fallback[res.status] || `Server error ${res.status}.`);
}

async function request(path: string, init?: RequestInit): Promise<Snapshot> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "Could not reach the server. Check your connection.");
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as Snapshot;
}

export async function getCurrent(): Promise<Snapshot> {
  if (isMockMode) return mockCurrent();
  return request("/api/current");
}

export async function uploadDocument(file: File): Promise<Snapshot> {
  const type = contentTypeFor(file);
  if (!type) throw new ApiError(415, "Unsupported format. Use PDF or text.");
  if (file.size > MAX_UPLOAD_BYTES) throw new ApiError(413, "The document is larger than 10 MB.");
  if (isMockMode) {
    await wait(1800);
    return mockUpload(type === "text/plain" ? await file.text() : SAMPLE_TEXT);
  }
  return request("/api/document", { method: "POST", headers: { "Content-Type": type }, body: file });
}

export async function rejectVersion(attempt: number, text: string, reason: string): Promise<Snapshot> {
  if (isMockMode) {
    await wait(1800);
    return mockReject(attempt, reason);
  }
  return request("/api/reject", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ attempt, text, reason }),
  });
}

export async function approveVersion(): Promise<Snapshot> {
  if (isMockMode) {
    await wait(500);
    return mockApprove();
  }
  return request("/api/approve", { method: "POST" });
}
