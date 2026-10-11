import {
  MOCK_AUDIO_URL,
  mockApprove,
  mockCurrent,
  mockReject,
  mockTrackRegion,
  mockUpdateRegions,
  mockUpload,
  mockUploadAudio,
  mockUploadMedia,
  SAMPLE_TEXT,
  wasSampleSubstituted,
} from "./mock";
import {
  ApiError,
  MAX_AUDIO_BYTES,
  MAX_IMAGE_BYTES,
  MAX_UPLOAD_BYTES,
  MAX_VIDEO_BYTES,
  type MediaRegion,
  type Snapshot,
} from "./types";

/** Local backend address used during development (set VITE_API_URL to it to go live). */
export const DEFAULT_API_URL = "http://127.0.0.1:8000";

const RAW = (import.meta.env["VITE_API_URL"] as string | undefined)?.trim();
const API_URL = RAW?.replace(/\/+$/, "");
export const isMockMode =
  !API_URL || import.meta.env["VITE_USE_MOCK"] === "true" || import.meta.env["MODE"] === "test";

/** File picker `accept` values. */
export const ACCEPT_DOCUMENTS = ".pdf,.txt,.md";
export const ACCEPT_AUDIO = ".mp3,.m4a,.wav";
export const ACCEPT_MEDIA = ".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm";

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function contentTypeFor(file: File): "application/pdf" | "text/plain" | null {
  const name = file.name.toLowerCase();
  if (file.type === "application/pdf" || name.endsWith(".pdf")) return "application/pdf";
  if (file.type.startsWith("text/") || name.endsWith(".txt") || name.endsWith(".md")) return "text/plain";
  return null;
}

/** The Content-Type the backend accepts for this audio file, or null if it is not mp3, m4a or wav. */
export function audioContentTypeFor(file: File): "audio/mpeg" | "audio/mp4" | "audio/wav" | null {
  const name = file.name.toLowerCase();
  if (file.type === "audio/mpeg" || file.type === "audio/mp3" || name.endsWith(".mp3")) return "audio/mpeg";
  if (file.type === "audio/mp4" || file.type === "audio/x-m4a" || file.type === "audio/m4a" || name.endsWith(".m4a"))
    return "audio/mp4";
  if (file.type === "audio/wav" || file.type === "audio/x-wav" || file.type === "audio/wave" || name.endsWith(".wav"))
    return "audio/wav";
  return null;
}

export const isAudioFile = (file: File): boolean => audioContentTypeFor(file) !== null;

export type MediaContentType =
  | "image/jpeg"
  | "image/png"
  | "image/webp"
  | "video/mp4"
  | "video/quicktime"
  | "video/webm";

/** The Content-Type the backend accepts for this image or video, or null if it is neither. */
export function mediaContentTypeFor(file: File): MediaContentType | null {
  const name = file.name.toLowerCase();
  const type = file.type.toLowerCase();
  if (type === "image/jpeg" || name.endsWith(".jpg") || name.endsWith(".jpeg")) return "image/jpeg";
  if (type === "image/png" || name.endsWith(".png")) return "image/png";
  if (type === "image/webp" || name.endsWith(".webp")) return "image/webp";
  if (type === "video/mp4" || name.endsWith(".mp4")) return "video/mp4";
  if (type === "video/quicktime" || name.endsWith(".mov")) return "video/quicktime";
  if (type === "video/webm" || name.endsWith(".webm")) return "video/webm";
  return null;
}

export const isMediaFile = (file: File): boolean => mediaContentTypeFor(file) !== null;
export const isVideoFile = (file: File): boolean => mediaContentTypeFor(file)?.startsWith("video/") ?? false;

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
    413: "The file is larger than the limit (10 MB documents, 25 MB audio, 20 MB images, 100 MB videos).",
    415: "Unsupported format. Use PDF or text, mp3/m4a/wav audio, or a JPEG/PNG/WebP image or MP4/MOV/WebM video.",
    422: "The document or the feedback could not be read.",
    502: "The model did not respond. The current version is unchanged; try again.",
    503: "Audio censoring is not available on this server (a key, ffmpeg or the image/video model is missing).",
  };
  return new ApiError(res.status, detail || fallback[res.status] || `Server error ${res.status}.`);
}

async function request<T = Snapshot>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "Could not reach the server. Check your connection.");
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
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
    if (type === "text/plain") return mockUpload(await file.text());
    return mockUpload(SAMPLE_TEXT, true, true);
  }
  return request("/api/document", { method: "POST", headers: { "Content-Type": type }, body: file });
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

/**
 * Sends an image or a video. Unlike the others this returns at once, with
 * `status: "processing"`: the analysis runs in the background, so call
 * `waitUntilSettled` to follow its `progress` until it is "ready" or "failed".
 * Sampled frames go to a third-party AI model (Gemini).
 */
export async function uploadMedia(file: File): Promise<Snapshot> {
  const type = mediaContentTypeFor(file);
  if (!type) throw new ApiError(415, "Unsupported format. Use a JPEG, PNG or WebP image or an MP4, MOV or WebM video.");
  const limit = type.startsWith("video/") ? MAX_VIDEO_BYTES : MAX_IMAGE_BYTES;
  if (file.size > limit) {
    throw new ApiError(413, type.startsWith("video/") ? "The video is larger than 100 MB." : "The image is larger than 20 MB.");
  }
  if (file.size === 0) throw new ApiError(422, "The file is empty.");
  if (isMockMode) {
    await wait(600);
    return mockUploadMedia(type.startsWith("video/") ? "video" : "image", file.name);
  }
  return request("/api/document", {
    method: "POST",
    headers: { "Content-Type": type, "X-File-Name": encodeURIComponent(file.name) },
    body: file,
  });
}

/** Sends a document, an audio file, an image or a video, whichever it is. */
export function uploadFile(file: File): Promise<Snapshot> {
  if (isMediaFile(file)) return uploadMedia(file);
  return isAudioFile(file) ? uploadAudio(file) : uploadDocument(file);
}

/** True while the backend is still working in the background (image/video analysis or export). */
export const isWorking = (snapshot: Snapshot): boolean =>
  snapshot.status === "processing" || snapshot.status === "exporting";

/**
 * Polls GET /api/current until the background work ends ("ready", "failed" or
 * approved), calling `onUpdate` with every snapshot so the UI can show
 * `progress`. Resolves with the final snapshot; stops early (resolving with
 * the last one) when `signal` is aborted.
 */
export async function waitUntilSettled(
  onUpdate: (snapshot: Snapshot) => void,
  signal?: AbortSignal,
  intervalMs = 1000,
): Promise<Snapshot> {
  let snapshot = await getCurrent();
  onUpdate(snapshot);
  while (isWorking(snapshot) && !signal?.aborted) {
    await wait(isMockMode ? Math.min(intervalMs, 400) : intervalMs);
    snapshot = await getCurrent();
    onUpdate(snapshot);
  }
  return snapshot;
}

/**
 * URL of the anonymized PDF (the uploaded PDF with each sensitive word erased
 * and a * in its place), or null when the document did not come from a PDF.
 * It is generated for the version under review, so the attempt is in the URL.
 */
export function anonymizedPdfUrl(snapshot: Snapshot): string | null {
  if (!snapshot.pdf_url) return null;
  if (isMockMode) return snapshot.pdf_url;
  return `${API_URL}${snapshot.pdf_url}?v=${snapshot.attempt}`;
}

/** URL of the original image/video under review (for the preview), or null. */
export function mediaSourceUrl(snapshot: Snapshot): string | null {
  const path = snapshot.media.source_url;
  if (!path) return null;
  if (isMockMode) return path;
  return `${API_URL}${path}?v=${snapshot.attempt}`;
}

/** URL to download the anonymized image/video once approved and exported, or null. */
export function mediaOutputUrl(snapshot: Snapshot): string | null {
  const path = snapshot.media.output_url;
  if (!path) return null;
  if (isMockMode) return path;
  return `${API_URL}${path}?v=${snapshot.attempt}`;
}

/**
 * Replaces the regions to hide with the edited list. `attempt` must be the
 * snapshot's (409 otherwise). Saving un-approves the version.
 */
export async function updateRegions(attempt: number, regions: MediaRegion[]): Promise<Snapshot> {
  if (isMockMode) {
    await wait(150);
    return mockUpdateRegions(attempt, regions);
  }
  return request("/api/media/regions", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ attempt, regions }),
  });
}

/**
 * Follows a manually drawn box through the video, forwards and backwards from
 * `seedTimeMs`, and returns the region with its keyframes filled in.
 */
export async function trackRegion(attempt: number, seedTimeMs: number, region: MediaRegion): Promise<MediaRegion> {
  if (isMockMode) {
    await wait(500);
    return mockTrackRegion(attempt, seedTimeMs, region);
  }
  return request<MediaRegion>("/api/media/track", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ attempt, seed_time_ms: seedTimeMs, region }),
  });
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
