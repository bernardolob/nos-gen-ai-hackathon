import { ApiError, EMPTY_SNAPSHOT, MAX_REASON_CHARS, type Snapshot } from "./types";

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

export function resetMock() {
  state = emptyState();
  source = "";
}

export async function mockUpload(text: string): Promise<Snapshot> {
  if (!text.trim()) throw new ApiError(422, "The document has no text.");
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
  if (attempt !== state.attempt) throw new ApiError(409, "The version under review has already changed.");
  if (reason.length > MAX_REASON_CHARS)
    throw new ApiError(422, "The feedback is longer than 2000 characters.");
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
  state = { ...state, approved: true };
  return structuredClone(state);
}
