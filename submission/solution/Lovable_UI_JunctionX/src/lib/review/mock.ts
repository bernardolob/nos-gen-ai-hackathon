import { ApiError, EMPTY_SNAPSHOT, MAX_REASON_CHARS, type Snapshot } from "./types";

/** In-memory mock of the review backend, following the same snapshot contract. */

export const SAMPLE_TEXT = `CLINICAL REPORT

Patient: Maria Conceição Oliveira Santos, born on 12/03/1968.
Address: 24 Rua das Flores, 4000-189 Porto. Phone: 912 345 678.
Tax ID 245789123. ID card 12345678.

The patient was seen at the clinic on 3 October 2026.
Reports a previous diagnosis of type 2 diabetes and hypertension.

Signed: Dr. João Pedro Almeida, licence 45678.`;

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

let state: Snapshot = { ...EMPTY_SNAPSHOT };
let source = "";

export function resetMock() {
  state = { ...EMPTY_SNAPSHOT };
  source = "";
}

export async function mockUpload(text: string): Promise<Snapshot> {
  if (!text.trim()) throw new ApiError(422, "The document has no text.");
  source = text;
  state = {
    has_document: true,
    attempt: 1,
    text: maskWords(source, false),
    approved: false,
    history: [],
    mode: "model",
    warnings: 1,
    issues: 0,
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
  state = {
    ...state,
    history: [...state.history, { attempt: state.attempt, text: state.text, reason }],
    attempt: state.attempt + 1,
    text: maskWords(source, state.attempt % 2 === 1),
    approved: false,
    warnings: 0,
  };
  return structuredClone(state);
}

export async function mockApprove(): Promise<Snapshot> {
  if (!state.has_document) throw new ApiError(409, "There is no document under review yet.");
  state = { ...state, approved: true };
  return structuredClone(state);
}
