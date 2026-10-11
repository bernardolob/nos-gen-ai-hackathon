export interface HistoryEntry {
  attempt: number;
  text: string;
  reason: string;
  /** Regions of the rejected version (image/video only), else null. */
  regions: number | null;
}

/* ---------------- Images and videos ---------------- */

export type RegionKind = "face" | "text" | "identity_document" | "plate" | "signature" | "biometric" | "code" | "other";
export type RegionSource = "gemini" | "face_detector" | "user";
/** How sure the analysis is, most to least. */
export type Confidence = "certo" | "provavel" | "incerto";

/** A box in normalized coordinates (0 to 1 of the image or frame). */
export interface RegionBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface RegionPoint {
  x: number;
  y: number;
}

/** The box (and, for faces, a 32-point outline inside it) at one instant. */
export interface RegionKeyframe {
  time_ms: number;
  box: RegionBox;
  polygon: RegionPoint[] | null;
}

/**
 * Something to hide. Never carries the recognised content: only the category
 * (e.g. "identificacao", "biometrico"), a generic reason, the confidence, the
 * origin, the time span (0 and 0 for images) and the keyframes.
 */
export interface MediaRegion {
  id: string;
  category: string;
  kind: RegionKind;
  reason: string;
  confidence: Confidence;
  source: RegionSource;
  start_ms: number;
  end_ms: number;
  keyframes: RegionKeyframe[];
}

/** The file under review. Empty for text and audio; `output_url` appears once exported. */
export interface MediaInfo {
  source_url: string;
  filename: string;
  width: number;
  height: number;
  duration_ms?: number;
  fps?: number;
  output_url?: string;
}

export interface MediaModel {
  id: string;
  capabilities: string[];
  verified: boolean;
}

/**
 * Image/video analysis and export run in the background: "processing" and
 * "exporting" mean poll again (GET /api/current); "failed" carries `error`.
 */
export type ReviewStatus = "idle" | "processing" | "exporting" | "ready" | "failed" | "approved";

/**
 * The backend names its stages in Portuguese (`progress.stage`). Show
 * `stageLabel(stage)`, never the raw value.
 */
export const STAGE_LABELS: Record<string, string> = {
  "validar imagem": "Checking the image",
  "analisar imagem": "Analysing the image",
  "análise concluída": "Analysis complete",
  "validar vídeo": "Checking the video",
  "extrair fotogramas": "Extracting frames",
  "detetar dados visuais": "Detecting sensitive visuals",
  "verificar dados residuais": "Checking for anything missed",
  "exportar imagem": "Exporting the image",
  "exportar vídeo": "Exporting the video",
  "exportação concluída": "Export complete",
  // Demo mode.
  analysing: "Analysing",
  exporting: "Exporting",
};

export const stageLabel = (stage: string): string => STAGE_LABELS[stage] ?? "Working";

export interface Progress {
  stage: string;
  completed: number;
  total: number;
}

/** What is under review: a text document (PDF or text), an audio file, an image or a video. */
export type ReviewKind = "text" | "audio" | "image" | "video";

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
  progress: Progress;
  warnings: number;
  issues: number;
  /** Path of the censored audio (e.g. "/api/audio/current"), or null. */
  audio_url: string | null;
  /** How many stretches of the audio were replaced by a sound (0 for text). */
  audio_ranges: number;
  /** Audio censoring is available (the backend has the key and ffmpeg). */
  audio_enabled: boolean;
  /** Image/video only (empty otherwise): source_url, size, duration, output_url... */
  media: Partial<MediaInfo>;
  /** Image/video only: the regions to hide (never any recognised text). */
  regions: MediaRegion[];
  /** Image/video only: the model that analysed it, or null. */
  model: MediaModel | null;
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
export const MAX_IMAGE_BYTES = 20 * 1024 * 1024;
export const MAX_VIDEO_BYTES = 100 * 1024 * 1024;
/** Videos longer than this (or larger than 1920x1080) are refused by the backend. */
export const MAX_VIDEO_SECONDS = 60;
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
