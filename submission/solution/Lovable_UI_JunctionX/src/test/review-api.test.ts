import { beforeEach, describe, expect, it } from "vitest";

import {
  audioContentTypeFor,
  censoredAudioUrl,
  contentTypeFor,
  DOCX_TYPE,
  isAudioFile,
  parseError,
  uploadAudio,
  uploadDocument,
  uploadFile,
  wasSampleSubstituted,
} from "@/lib/review/api";
import {
  mockApprove,
  mockReject,
  mockUpload,
  mockUploadAudio,
  resetMock,
  SAMPLE_TRANSCRIPT,
} from "@/lib/review/mock";
import { EMPTY_SNAPSHOT, MAX_AUDIO_BYTES } from "@/lib/review/types";

describe("review contract", () => {
  beforeEach(() => resetMock());

  it("reject returns attempt+1 and stores the rejected version in history", async () => {
    const first = await mockUpload("Utente Maria Santos, NIF 245789123.");
    const next = await mockReject(first.attempt, "ocultar mais");
    expect(next.attempt).toBe(2);
    expect(next.history).toEqual([
      { attempt: 1, text: first.text, reason: "ocultar mais", regions: null },
    ]);
  });

  it("reject with a stale attempt fails with 409", async () => {
    await mockUpload("Utente Maria Santos.");
    await expect(mockReject(5, "x")).rejects.toMatchObject({ status: 409 });
  });

  it("uploads PDFs as application/pdf and text files as text/plain", () => {
    expect(contentTypeFor(new File(["x"], "a.pdf"))).toBe("application/pdf");
    expect(contentTypeFor(new File(["x"], "a.txt"))).toBe("text/plain");
    expect(contentTypeFor(new File(["x"], "a.docx"))).toBe(DOCX_TYPE);
    expect(contentTypeFor(new File(["x"], "a.doc"))).toBeNull();
  });

  it("falls back to an English message for known error statuses", async () => {
    const res = new Response(JSON.stringify({ detail: 42 }), { status: 502 });
    const err = await parseError(res);
    expect(err.status).toBe(502);
    expect(err.message).toBe(
      "The model did not respond. The current version is unchanged; try again.",
    );
  });

  it("passes through the backend's detail message", async () => {
    const res = new Response(
      JSON.stringify({ detail: "The version under review has already changed." }),
      { status: 409 },
    );
    const err = await parseError(res);
    expect(err.status).toBe(409);
    expect(err.message).toBe("The version under review has already changed.");
  });

  it("has a fallback for the audio-only statuses", async () => {
    const off = await parseError(new Response("{}", { status: 503 }));
    expect(off.message).toContain("Audio censoring is not available");
    const none = await parseError(new Response("{}", { status: 404 }));
    expect(none.message).toBe("There is no censored audio yet.");
  });
});

describe("text snapshot", () => {
  beforeEach(() => resetMock());

  it("has no audio", async () => {
    const snap = await mockUpload("Utente Maria Santos.");
    expect(snap.kind).toBe("text");
    expect(snap.audio_url).toBeNull();
    expect(snap.audio_ranges).toBe(0);
    expect(censoredAudioUrl(snap)).toBeNull();
  });

  it("the empty snapshot is text, with no audio and audio off", () => {
    expect(EMPTY_SNAPSHOT).toMatchObject({
      kind: "text",
      audio_url: null,
      audio_ranges: 0,
      audio_enabled: false,
    });
  });
});

describe("audio contract", () => {
  beforeEach(() => resetMock());

  it("maps mp3, m4a and wav to the content types the backend accepts", () => {
    expect(audioContentTypeFor(new File(["x"], "a.mp3"))).toBe("audio/mpeg");
    expect(audioContentTypeFor(new File(["x"], "a.m4a"))).toBe("audio/mp4");
    expect(audioContentTypeFor(new File(["x"], "a.wav"))).toBe("audio/wav");
    expect(audioContentTypeFor(new File(["x"], "a", { type: "audio/x-m4a" }))).toBe("audio/mp4");
    expect(audioContentTypeFor(new File(["x"], "a.ogg"))).toBeNull();
    expect(audioContentTypeFor(new File(["x"], "a.pdf"))).toBeNull();
  });

  it("tells audio files from documents", () => {
    expect(isAudioFile(new File(["x"], "a.mp3"))).toBe(true);
    expect(isAudioFile(new File(["x"], "a.pdf"))).toBe(false);
    expect(isAudioFile(new File(["x"], "a.txt"))).toBe(false);
  });

  it("the mock audio snapshot follows the backend contract", async () => {
    const snap = await mockUploadAudio();
    expect(snap).toMatchObject({
      has_document: true,
      kind: "audio",
      attempt: 1,
      approved: false,
      audio_url: "/api/audio/current",
      audio_enabled: true,
    });
    expect(snap.text.split("\n")).toHaveLength(SAMPLE_TRANSCRIPT.split("\n").length);
    // "Maria Santos" is two masked words but one stretch of audio, like the backend
    expect(snap.text).toContain("is * *.");
    expect(snap.audio_ranges).toBe(3);
  });

  it("the censored audio URL is playable in demo mode and null without audio", async () => {
    const snap = await mockUploadAudio();
    expect(censoredAudioUrl(snap)).toMatch(/^data:audio\/wav;base64,/);
    expect(censoredAudioUrl({ ...snap, audio_url: null })).toBeNull();
  });

  it("rejecting audio keeps it audio, bumps the attempt and updates the ranges", async () => {
    const first = await mockUploadAudio();
    const next = await mockReject(first.attempt, "also hide the diagnosis");
    expect(next.kind).toBe("audio");
    expect(next.attempt).toBe(2);
    expect(next.audio_url).toBe("/api/audio/current");
    expect(next.audio_ranges).toBeGreaterThan(first.audio_ranges);
    expect(next.history).toEqual([
      { attempt: 1, text: first.text, reason: "also hide the diagnosis", regions: null },
    ]);
  });

  it("approving audio keeps the audio fields", async () => {
    await mockUploadAudio();
    const done = await mockApprove();
    expect(done).toMatchObject({ approved: true, kind: "audio", audio_url: "/api/audio/current" });
  });

  it("uploading a text document after audio resets to text", async () => {
    await mockUploadAudio();
    const snap = await mockUpload("Utente Maria Santos.");
    expect(snap).toMatchObject({ kind: "text", audio_url: null, audio_ranges: 0, attempt: 1 });
  });

  it("refuses unsupported, empty and oversized audio before sending", async () => {
    await expect(uploadAudio(new File(["x"], "a.ogg"))).rejects.toMatchObject({ status: 415 });
    await expect(uploadAudio(new File([], "a.mp3"))).rejects.toMatchObject({ status: 422 });
    const huge = new File(["x"], "a.mp3");
    Object.defineProperty(huge, "size", { value: MAX_AUDIO_BYTES + 1 });
    await expect(uploadAudio(huge)).rejects.toMatchObject({ status: 413 });
  });

  it("uploadFile sends audio to the audio route and documents to the document route", async () => {
    const audio = await uploadFile(new File(["x"], "a.mp3"));
    expect(audio.kind).toBe("audio");
    // a PDF: the demo does not read it (jsdom files have no .text())
    const doc = await uploadFile(new File(["x"], "a.pdf"));
    expect(doc.kind).toBe("document");
    expect(doc.document?.format).toBe("pdf");
  }, 15000);
});

describe("sample substitution notice", () => {
  beforeEach(() => resetMock());

  it("flags a PDF in demo mode as the sample, not the file's content", async () => {
    await uploadDocument(new File(["x"], "cv.pdf"));
    expect(wasSampleSubstituted()).toBe(true);
  }, 15000);

  it("does not flag a text file: its own content is used", async () => {
    await mockUpload("Utente Maria Santos.");
    expect(wasSampleSubstituted()).toBe(false);
  });

  it("audio is always the sample transcript, never the real file", async () => {
    await mockUploadAudio();
    expect(wasSampleSubstituted()).toBe(true);
  });

  it("resetMock clears the flag", async () => {
    await uploadDocument(new File(["x"], "cv.pdf"));
    expect(wasSampleSubstituted()).toBe(true);
    resetMock();
    expect(wasSampleSubstituted()).toBe(false);
  }, 15000);
});
