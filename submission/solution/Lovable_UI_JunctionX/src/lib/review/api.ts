import {
  MOCK_AUDIO_URL,
  mockApprove,
  mockCurrent,
  mockReject,
  mockUpload,
  mockUploadAudio,
  mockUploadDocument,
  mockDocumentRegions,
  wasSampleSubstituted,
} from "./mock";
import { ApiError, MAX_AUDIO_BYTES, MAX_UPLOAD_BYTES, type Snapshot } from "./types";
import type { MediaRegion } from "@/components/review/media-editor";

/** Local backend address used during development (set VITE_API_URL to it to go live). */
export const DEFAULT_API_URL = "http://127.0.0.1:8000";

const RAW = (import.meta.env["VITE_API_URL"] as string | undefined)?.trim();
const API_URL = RAW?.replace(/\/+$/, "");
/** Mock mode when VITE_API_URL is unset or VITE_USE_MOCK=true, so the preview keeps working. */
export const isMockMode = !API_URL || import.meta.env["VITE_USE_MOCK"] === "true";

/** File picker `accept` values. */
export const ACCEPT_DOCUMENTS = ".pdf,.docx,.txt,.md";
export const DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
export const reviewApiUrl = API_URL ?? "";
export const ACCEPT_AUDIO = ".mp3,.m4a,.wav";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function contentTypeFor(
  file: File,
): "application/pdf" | "text/plain" | typeof DOCX_TYPE | null {
  const name = file.name.toLowerCase();
  if (file.type === "application/pdf" || name.endsWith(".pdf")) return "application/pdf";
  if (file.type === DOCX_TYPE || name.endsWith(".docx")) return DOCX_TYPE;
  if (file.type.startsWith("text/") || name.endsWith(".txt") || name.endsWith(".md"))
    return "text/plain";
  return null;
}

/** The Content-Type the backend accepts for this audio file, or null if it is not mp3, m4a or wav. */
export function audioContentTypeFor(file: File): "audio/mpeg" | "audio/mp4" | "audio/wav" | null {
  const name = file.name.toLowerCase();
  if (file.type === "audio/mpeg" || file.type === "audio/mp3" || name.endsWith(".mp3"))
    return "audio/mpeg";
  if (
    file.type === "audio/mp4" ||
    file.type === "audio/x-m4a" ||
    file.type === "audio/m4a" ||
    name.endsWith(".m4a")
  )
    return "audio/mp4";
  if (
    file.type === "audio/wav" ||
    file.type === "audio/x-wav" ||
    file.type === "audio/wave" ||
    name.endsWith(".wav")
  )
    return "audio/wav";
  return null;
}

export const isAudioFile = (file: File): boolean => audioContentTypeFor(file) !== null;

export { wasSampleSubstituted };

export async function parseError(res: Response): Promise<ApiError> {
  let detail = "";
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    /* body is not JSON */
  }
  const fallback: Record<number, string> = {
    404: "There is no censored audio yet.",
    409: "The version under review has changed. Refresh and try again.",
    413: "The file is larger than the limit (10 MB for documents, 25 MB for audio).",
    415: "Unsupported format. Use PDF, DOCX or text (or mp3, m4a or wav for audio).",
    422: "The document or the feedback could not be read.",
    502: "The model did not respond. The current version is unchanged; try again.",
    503: "Audio censoring is not available on this server (the ElevenLabs key or ffmpeg is missing).",
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
  if (!type) throw new ApiError(415, "Unsupported format. Use PDF, DOCX or text.");
  if (file.size > MAX_UPLOAD_BYTES) throw new ApiError(413, "The document is larger than 10 MB.");
  if (isMockMode) {
    await wait(1800);
    if (type === "text/plain") return mockUpload(await file.text());
    return mockUploadDocument(type === DOCX_TYPE ? "docx" : "pdf", file.name);
  }
  return request("/api/document", {
    method: "POST",
    headers: { "Content-Type": type, "X-File-Name": encodeURIComponent(file.name) },
    body: file,
  });
}

export async function saveDocumentRegions(
  imageId: string,
  attempt: number,
  regions: MediaRegion[],
): Promise<Snapshot> {
  if (isMockMode) return mockDocumentRegions(imageId, attempt, regions);
  return request(`/api/document/images/${encodeURIComponent(imageId)}/regions`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ attempt, regions }),
  });
}

export function documentOutputUrl(snapshot: Snapshot): string | null {
  const path = snapshot.document?.output_url;
  return snapshot.approved && path ? `${API_URL}${path}` : null;
}

/**
 * Sends an audio file. The backend transcribes it (the ORIGINAL audio, still
 * with the sensitive data, goes to ElevenLabs), masks the transcript and
 * replaces each masked word in the audio with a sound.
 */
export async function uploadAudio(file: File): Promise<Snapshot> {
  const type = audioContentTypeFor(file);
  if (!type) throw new ApiError(415, "Unsupported format. Use mp3, m4a or wav.");
  if (file.size > MAX_AUDIO_BYTES) throw new ApiError(413, "The audio is larger than 25 MB.");
  if (file.size === 0) throw new ApiError(422, "The audio is empty.");
  if (isMockMode) {
    await wait(2500);
    return mockUploadAudio();
  }
  return request("/api/audio", { method: "POST", headers: { "Content-Type": type }, body: file });
}

/** Sends a document or an audio file, whichever it is. */
export function uploadFile(file: File): Promise<Snapshot> {
  return isAudioFile(file) ? uploadAudio(file) : uploadDocument(file);
}

/**
 * The URL to play the censored audio of the current version, or null when
 * there is none. The version is added to the URL so the browser does not
 * reuse the audio of a previous attempt.
 */
export function censoredAudioUrl(snapshot: Snapshot): string | null {
  if (!snapshot.audio_url) return null;
  if (isMockMode) return MOCK_AUDIO_URL;
  return `${API_URL}${snapshot.audio_url}?v=${snapshot.attempt}`;
}

export async function rejectVersion(
  attempt: number,
  text: string,
  reason: string,
  documentId?: string,
): Promise<Snapshot> {
  if (isMockMode) {
    await wait(1800);
    return mockReject(attempt, reason);
  }
  return request("/api/reject", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ attempt, text, reason, document_id: documentId }),
  });
}

export async function approveVersion(attempt?: number, documentId?: string): Promise<Snapshot> {
  if (isMockMode) {
    await wait(500);
    return mockApprove();
  }
  return request("/api/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: documentId ? JSON.stringify({ attempt, document_id: documentId }) : null,
  });
}
