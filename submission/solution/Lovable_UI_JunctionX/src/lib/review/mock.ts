import { ApiError, EMPTY_SNAPSHOT, MAX_REASON_CHARS, type Snapshot } from "./types";
import type { MediaRegion } from "@/components/review/media-editor";

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
        const isName =
          offset > 0 && /^\p{Lu}\p{Ll}+$/u.test(clean) && !/^(Dr|Tax|Phone)$/.test(clean);
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
    status: "ready",
  };
  return structuredClone(state);
}

export async function mockUploadDocument(
  format: "pdf" | "docx",
  filename: string,
): Promise<Snapshot> {
  await mockUpload(SAMPLE_TEXT, true);
  const sample = `<svg xmlns="http://www.w3.org/2000/svg" width="480" height="240"><rect width="480" height="240" fill="#e2e8f0"/><rect x="24" y="24" width="144" height="192" rx="8" fill="#64748b"/><circle cx="96" cy="86" r="36" fill="#cbd5e1"/><path d="M40 192v-24a56 56 0 0 1 112 0v24" fill="#cbd5e1"/><text x="200" y="70" font-size="20">SAMPLE DOCUMENT</text><text x="200" y="110" font-size="16">Name: Maria Santos</text><text x="200" y="145" font-size="16">ID: 123456789</text></svg>`;
  state = {
    ...state,
    kind: "document",
    document: {
      id: "demo-document",
      format,
      filename,
      output_url: null,
      images: [
        {
          id: "demo-image",
          width: 480,
          height: 240,
          source_url: `data:image/svg+xml,${encodeURIComponent(sample)}`,
          placements: [format === "pdf" ? "Page 1" : "Body · image 1"],
          regions: [
            {
              id: "demo-mask",
              category: "identificacao",
              kind: "text",
              confidence: "certo",
              source: "gemini",
              reason: "Sample identifying details",
              start_ms: 0,
              end_ms: 0,
              keyframes: [{ time_ms: 0, box: { x: 0.4, y: 0.34, width: 0.55, height: 0.32 } }],
            },
          ],
        },
      ],
    },
  };
  return structuredClone(state);
}

export async function mockDocumentRegions(
  imageId: string,
  attempt: number,
  regions: MediaRegion[],
): Promise<Snapshot> {
  if (state.approved || attempt !== state.attempt)
    throw new ApiError(409, "The version under review has changed.");
  if (!state.document?.images.some((image) => image.id === imageId))
    throw new ApiError(404, "Image not found.");
  state = {
    ...state,
    document: {
      ...state.document,
      images: state.document.images.map((image) =>
        image.id === imageId ? { ...image, regions: structuredClone(regions) } : image,
      ),
    },
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

export async function mockCurrent(): Promise<Snapshot> {
  return structuredClone(state);
}

export async function mockReject(attempt: number, reason: string): Promise<Snapshot> {
  if (!state.has_document) throw new ApiError(409, "There is no document under review yet.");
  if (attempt !== state.attempt)
    throw new ApiError(409, "The version under review has already changed.");
  if (reason.length > MAX_REASON_CHARS)
    throw new ApiError(422, "The feedback is longer than 2000 characters.");
  const text = maskWords(source, state.attempt % 2 === 1);
  state = {
    ...state,
    history: [
      ...state.history,
      { attempt: state.attempt, text: state.text, reason, regions: null },
    ],
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
  state = { ...state, approved: true };
  return structuredClone(state);
}
