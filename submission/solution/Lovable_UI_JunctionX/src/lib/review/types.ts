export interface HistoryEntry {
  attempt: number;
  text: string;
  reason: string;
  /** Regions of the rejected version (image/video only), else null. */
  regions: number | null;
}

/** What is under review: a text document (PDF or text) or an audio file. */
export type ReviewKind = "text" | "audio" | "image" | "video";

/** Where an image/video review is: analysis or export running, done, or failed. */
export type ReviewStatus = "idle" | "processing" | "exporting" | "ready" | "failed" | "approved";

/**
 * The review state, exactly as the backend returns it (GET /api/current and
 * every other route). The UI never derives versions locally.
 *
 * For audio, `text` is the masked transcript and the censored audio is served
 * at `audio_url` (see `censoredAudioUrl` in api.ts).
 */
export interface Snapshot {
  has_document: boolean;
  kind: ReviewKind;
  attempt: number;
  text: string;
  approved: boolean;
  history: HistoryEntry[];
  /** "multimodal" is an image or video review. */
  mode: "model" | "rules" | "multimodal";
  status: ReviewStatus;
  progress: { stage: string; completed: number; total: number };
  warnings: number;
  issues: number;
  /** Path of the censored audio (e.g. "/api/audio/current"), or null. */
  audio_url: string | null;
  /** How many stretches of the audio were replaced by a sound (0 for text). */
  audio_ranges: number;
  /** Audio censoring is available (the backend has the key and ffmpeg). */
  audio_enabled: boolean;
  /** Image/video only (empty otherwise): source_url, size, duration, output_url... */
  media: Record<string, unknown>;
  /** Image/video only: the regions to hide (never any recognised text). */
  regions: Record<string, unknown>[];
  /** Image/video only: the model that analysed it, or null. */
  model: Record<string, unknown> | null;
  /** Image/video only: why the analysis failed, or "". */
  error: string;
}

export const EMPTY_SNAPSHOT: Snapshot = {
  has_document: false,
  kind: "text",
  attempt: 0,
  text: "",
  approved: false,
  history: [],
  mode: "model",
  warnings: 0,
  issues: 0,
  audio_url: null,
  audio_ranges: 0,
  audio_enabled: false,
  status: "idle",
  progress: { stage: "", completed: 0, total: 0 },
  media: {},
  regions: [],
  model: null,
  error: "",
};

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const MAX_AUDIO_BYTES = 25 * 1024 * 1024;
export const MAX_REASON_CHARS = 2000;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
