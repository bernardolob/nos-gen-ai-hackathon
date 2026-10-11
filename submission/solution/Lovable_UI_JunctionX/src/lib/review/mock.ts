import { MOCK_IMAGE_SIZE, MOCK_IMAGE_URL, MOCK_VIDEO_SIZE, MOCK_VIDEO_URL } from "./mock-media";
import { ApiError, EMPTY_SNAPSHOT, MAX_REASON_CHARS, type MediaRegion, type Snapshot } from "./types";

/** In-memory mock of the review backend, following the same snapshot contract. */

export const SAMPLE_TEXT = `CLINICAL REPORT

Patient: Maria Conceição Oliveira Santos, born on 12/03/1968.
Address: 24 Rua das Flores, 4000-189 Porto. Phone: 912 345 678.
Tax ID 245789123. ID card 12345678.

The patient was seen at the clinic on 3 October 2026.
Reports a previous diagnosis of type 2 diabetes and hypertension.

Signed: Dr. João Pedro Almeida, licence 45678.`;

/** What the mock audio "says": the transcript the backend would produce. */
export const SAMPLE_TRANSCRIPT = `Good morning, my name is Maria Santos.
My tax ID is 245789123 and my phone is 912345678.
I was diagnosed with diabetes and hypertension last year.`;

/** Replaces each sensitive word with a single '*'. Strict mode also masks clinical terms. */
export function maskWords(text: string, strict: boolean): string {
  const clinical = /^(diabetes|hypertension)$/i;
  return text
    .split("\n")
    .map((line) =>
      line.replace(/[\p{L}\p{N}][\p{L}\p{N}/.-]*/gu, (word, offset: number) => {
        const clean = word.replace(/[.,]+$/, "");
        const suffix = word.slice(clean.length);
        const hasDigit = /\d/.test(clean);
        const isName = offset > 0 && /^\p{Lu}\p{Ll}+$/u.test(clean) && !/^(Dr|Tax|Phone)$/.test(clean);
        if (hasDigit || isName || (strict && clinical.test(clean))) return "*" + suffix;
        return word;
      }),
    )
    .join("\n");
}

/**
 * How many stretches of the audio are replaced by a sound. Like the backend,
 * consecutive masked words on a line are one stretch ("* *" is one, not two).
 */
export const countRanges = (text: string): number =>
  text.split("\n").reduce((total, line) => total + (line.match(/\*(?: \*)*/g) ?? []).length, 0);

/** A short silent WAV as a data URI, so the audio player works in demo mode. */
function silentWavUri(seconds = 2, sampleRate = 8000): string {
  const samples = seconds * sampleRate;
  const buffer = new ArrayBuffer(44 + samples);
  const view = new DataView(buffer);
  const write = (offset: number, text: string) => {
    for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
  };
  write(0, "RIFF");
  view.setUint32(4, 36 + samples, true);
  write(8, "WAVEfmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate, true);
  view.setUint16(32, 1, true);
  view.setUint16(34, 8, true); // 8 bits
  write(36, "data");
  view.setUint32(40, samples, true);
  new Uint8Array(buffer, 44).fill(128); // 8-bit silence
  let binary = "";
  new Uint8Array(buffer).forEach((byte) => (binary += String.fromCharCode(byte)));
  return `data:audio/wav;base64,${btoa(binary)}`;
}

export const MOCK_AUDIO_URL = silentWavUri();

const AUDIO_PATH = "/api/audio/current";

const emptyState = (): Snapshot => ({ ...EMPTY_SNAPSHOT, audio_enabled: true });

let state: Snapshot = emptyState();
let source = "";

/**
 * True right after an upload whose result is the canned sample, not the
 * file the person actually chose (demo mode cannot read a PDF client-side,
 * and the audio mock always "hears" the same transcript). The UI uses this
 * to warn that what is shown is not their document.
 */
let sampleSubstituted = false;

export function wasSampleSubstituted(): boolean {
  return sampleSubstituted;
}

export function resetMock() {
  state = emptyState();
  source = "";
  sampleSubstituted = false;
}

export async function mockUpload(text: string, usedSample = false): Promise<Snapshot> {
  if (!text.trim()) throw new ApiError(422, "The document has no text.");
  sampleSubstituted = usedSample;
  source = text;
  state = {
    ...emptyState(),
    has_document: true,
    kind: "text",
    attempt: 1,
    text: maskWords(source, false),
    warnings: 1,
  };
  return structuredClone(state);
}

/** The mock audio is always the same sample: it "says" SAMPLE_TRANSCRIPT. */
export async function mockUploadAudio(): Promise<Snapshot> {
  sampleSubstituted = true;
  source = SAMPLE_TRANSCRIPT;
  const text = maskWords(source, false);
  state = {
    ...emptyState(),
    has_document: true,
    kind: "audio",
    attempt: 1,
    text,
    audio_url: AUDIO_PATH,
    audio_ranges: countRanges(text),
  };
  return structuredClone(state);
}

/* ---------------- Images and videos ---------------- */

/** How many polls the fake background work takes, so the progress UI can be seen. */
const MOCK_STEPS = 4;
let ticks = 0;

const box = (x: number, y: number, width: number, height: number) => ({ x, y, width, height });

const region = (
  id: string,
  kind: MediaRegion["kind"],
  category: string,
  reason: string,
  keyframes: MediaRegion["keyframes"],
  end_ms = 0,
): MediaRegion => ({
  id,
  kind,
  category,
  reason,
  confidence: "certo",
  source: kind === "face" ? "face_detector" : "gemini",
  start_ms: 0,
  end_ms,
  keyframes,
});

/** What the "analysis" finds. Coordinates match the drawing in mock-media.ts. */
function mockRegions(kind: "image" | "video"): MediaRegion[] {
  if (kind === "image") {
    return [
      region("r-face", "face", "biometrico", "A face that identifies a person.", [
        { time_ms: 0, box: box(0.19, 0.1, 0.16, 0.26), polygon: null },
      ]),
      region("r-id", "identity_document", "identificacao", "An identity document.", [
        { time_ms: 0, box: box(0.51, 0.22, 0.36, 0.36), polygon: null },
      ]),
      region("r-plate", "plate", "identificacao", "A vehicle licence plate.", [
        { time_ms: 0, box: box(0.59, 0.8, 0.24, 0.12), polygon: null },
      ]),
    ];
  }
  return [
    region(
      "r-face",
      "face",
      "biometrico",
      "A face that identifies a person.",
      [
        { time_ms: 0, box: box(0.15, 0.2, 0.2, 0.35), polygon: null },
        { time_ms: 1000, box: box(0.4, 0.2, 0.2, 0.35), polygon: null },
        { time_ms: 2000, box: box(0.65, 0.2, 0.2, 0.35), polygon: null },
      ],
      2000,
    ),
  ];
}

export async function mockUploadMedia(kind: "image" | "video", filename: string): Promise<Snapshot> {
  sampleSubstituted = false;
  source = "";
  ticks = 0;
  const size = kind === "image" ? MOCK_IMAGE_SIZE : MOCK_VIDEO_SIZE;
  state = {
    ...emptyState(),
    has_document: true,
    kind,
    status: "processing",
    progress: { stage: "analysing", completed: 0, total: MOCK_STEPS },
    attempt: 1,
    media: {
      source_url: kind === "image" ? MOCK_IMAGE_URL : MOCK_VIDEO_URL,
      filename,
      ...size,
    },
    mode: "multimodal",
    model: { id: "demo-model", capabilities: ["image", "video", "json"], verified: true },
  };
  return structuredClone(state);
}

/** Advances the fake background work by one poll. */
function advance() {
  if (state.status !== "processing" && state.status !== "exporting") return;
  ticks += 1;
  const exporting = state.status === "exporting";
  if (ticks < MOCK_STEPS) {
    state = {
      ...state,
      progress: { stage: exporting ? "exporting" : "analysing", completed: ticks, total: MOCK_STEPS },
    };
    return;
  }
  ticks = 0;
  state = exporting
    ? {
        ...state,
        status: "ready",
        approved: true,
        progress: { stage: "", completed: 0, total: 0 },
        media: { ...state.media, output_url: state.media.source_url ?? "" },
      }
    : {
        ...state,
        status: "ready",
        progress: { stage: "", completed: 0, total: 0 },
        regions: state.regions.length ? state.regions : mockRegions(state.kind === "video" ? "video" : "image"),
      };
}

export async function mockUpdateRegions(attempt: number, regions: MediaRegion[]): Promise<Snapshot> {
  if (state.kind !== "image" && state.kind !== "video") throw new ApiError(409, "There is no image or video yet.");
  if (state.status !== "ready") throw new ApiError(409, "The analysis has not finished yet.");
  if (attempt !== state.attempt) throw new ApiError(409, "The version under review has already changed.");
  for (const r of regions) {
    if (r.end_ms < r.start_ms) throw new ApiError(422, "A hiding interval is not valid.");
    if (state.kind === "image" && (r.start_ms !== 0 || r.end_ms !== 0))
      throw new ApiError(422, "An image region must use 0 ms.");
    if (state.kind === "video" && r.end_ms > (state.media.duration_ms ?? 0))
      throw new ApiError(422, "A region goes past the end of the video.");
  }
  const media = { ...state.media };
  delete media.output_url;
  state = { ...state, regions: structuredClone(regions), approved: false, media };
  return structuredClone(state);
}

/** Pretends to follow a box: keeps it still, with a keyframe every 500 ms of the video. */
export async function mockTrackRegion(attempt: number, seedTimeMs: number, r: MediaRegion): Promise<MediaRegion> {
  if (state.kind !== "video") throw new ApiError(409, "Only a video can be tracked.");
  if (attempt !== state.attempt) throw new ApiError(409, "The version under review has already changed.");
  const duration = state.media.duration_ms ?? 0;
  if (seedTimeMs < 0 || seedTimeMs > duration) throw new ApiError(422, "The tracking instant is not valid.");
  const seed = r.keyframes[0]?.box ?? box(0.4, 0.4, 0.2, 0.2);
  const keyframes: MediaRegion["keyframes"] = [];
  for (let t = 0; t <= duration; t += 500) keyframes.push({ time_ms: t, box: { ...seed }, polygon: null });
  return { ...structuredClone(r), start_ms: 0, end_ms: duration, keyframes };
}

export async function mockCurrent(): Promise<Snapshot> {
  advance();
  return structuredClone(state);
}

export async function mockReject(attempt: number, reason: string): Promise<Snapshot> {
  if (!state.has_document) throw new ApiError(409, "There is no document under review yet.");
  if (attempt !== state.attempt) throw new ApiError(409, "The version under review has already changed.");
  if (reason.length > MAX_REASON_CHARS)
    throw new ApiError(422, "The feedback is longer than 2000 characters.");
  if (state.kind === "image" || state.kind === "video") {
    if (state.status !== "ready") throw new ApiError(409, "The analysis has not finished yet.");
    ticks = 0;
    state = {
      ...state,
      history: [...state.history, { attempt: state.attempt, text: "", reason, regions: state.regions.length }],
      attempt: state.attempt + 1,
      status: "processing",
      progress: { stage: "analysing", completed: 0, total: MOCK_STEPS },
      approved: false,
    };
    return structuredClone(state);
  }
  const text = maskWords(source, state.attempt % 2 === 1);
  state = {
    ...state,
    history: [...state.history, { attempt: state.attempt, text: state.text, reason, regions: null }],
    attempt: state.attempt + 1,
    text,
    approved: false,
    warnings: 0,
    audio_ranges: state.kind === "audio" ? countRanges(text) : 0,
  };
  return structuredClone(state);
}

export async function mockApprove(): Promise<Snapshot> {
  if (!state.has_document) throw new ApiError(409, "There is no document under review yet.");
  if (state.kind === "image" || state.kind === "video") {
    if (state.status !== "ready") throw new ApiError(409, "The analysis has not finished yet.");
    ticks = 0;
    state = {
      ...state,
      status: "exporting",
      progress: { stage: "exporting", completed: 0, total: MOCK_STEPS },
    };
    return structuredClone(state);
  }
  state = { ...state, approved: true };
  return structuredClone(state);
}
