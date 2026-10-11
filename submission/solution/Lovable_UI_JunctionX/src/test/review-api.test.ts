import { beforeEach, describe, expect, it } from "vitest";

import {
  approveVersion,
  audioContentTypeFor,
  censoredAudioUrl,
  contentTypeFor,
  getCurrent,
  isAudioFile,
  isMediaFile,
  isVideoFile,
  mediaContentTypeFor,
  mediaOutputUrl,
  mediaSourceUrl,
  parseError,
  rejectVersion,
  trackRegion,
  updateRegions,
  uploadAudio,
  uploadDocument,
  uploadFile,
  uploadMedia,
  waitUntilSettled,
  wasSampleSubstituted,
} from "@/lib/review/api";
import { mockApprove, mockReject, mockUpload, mockUploadAudio, resetMock, SAMPLE_TRANSCRIPT } from "@/lib/review/mock";
import { EMPTY_SNAPSHOT, MAX_AUDIO_BYTES, MAX_IMAGE_BYTES, type Snapshot } from "@/lib/review/types";

describe("review contract", () => {
  beforeEach(() => resetMock());

  it("reject returns attempt+1 and stores the rejected version in history", async () => {
    const first = await mockUpload("Utente Maria Santos, NIF 245789123.");
    const next = await mockReject(first.attempt, "ocultar mais");
    expect(next.attempt).toBe(2);
    expect(next.history).toEqual([{ attempt: 1, text: first.text, reason: "ocultar mais", regions: null }]);
  });

  it("reject with a stale attempt fails with 409", async () => {
    await mockUpload("Utente Maria Santos.");
    await expect(mockReject(5, "x")).rejects.toMatchObject({ status: 409 });
  });

  it("uploads PDFs as application/pdf and text files as text/plain", () => {
    expect(contentTypeFor(new File(["x"], "a.pdf"))).toBe("application/pdf");
    expect(contentTypeFor(new File(["x"], "a.txt"))).toBe("text/plain");
    expect(contentTypeFor(new File(["x"], "a.docx"))).toBeNull();
  });

  it("falls back to an English message for known error statuses", async () => {
    const res = new Response(JSON.stringify({ detail: 42 }), { status: 502 });
    const err = await parseError(res);
    expect(err.status).toBe(502);
    expect(err.message).toBe("The model did not respond. The current version is unchanged; try again.");
  });

  it("passes through the backend's detail message", async () => {
    const res = new Response(JSON.stringify({ detail: "The version under review has already changed." }), { status: 409 });
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
    expect(EMPTY_SNAPSHOT).toMatchObject({ kind: "text", audio_url: null, audio_ranges: 0, audio_enabled: false });
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
    expect(next.history).toEqual([{ attempt: 1, text: first.text, reason: "also hide the diagnosis", regions: null }]);
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
    expect(doc.kind).toBe("text");
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

describe("image and video contract (demo mode)", () => {
  beforeEach(() => resetMock());

  const image = () => new File(["x"], "photo.JPG", { type: "" });
  const video = () => new File(["x"], "clip.mov", { type: "video/quicktime" });

  it("maps files to the content types the backend accepts", () => {
    expect(mediaContentTypeFor(image())).toBe("image/jpeg");
    expect(mediaContentTypeFor(new File(["x"], "a.png"))).toBe("image/png");
    expect(mediaContentTypeFor(new File(["x"], "a.webp"))).toBe("image/webp");
    expect(mediaContentTypeFor(video())).toBe("video/quicktime");
    expect(mediaContentTypeFor(new File(["x"], "a.webm"))).toBe("video/webm");
    expect(mediaContentTypeFor(new File(["x"], "a.pdf"))).toBeNull();
    expect(isMediaFile(image())).toBe(true);
    expect(isVideoFile(video())).toBe(true);
    expect(isVideoFile(image())).toBe(false);
  });

  it("refuses unsupported, empty and oversize files before sending", async () => {
    await expect(uploadMedia(new File(["x"], "a.gif"))).rejects.toMatchObject({ status: 415 });
    await expect(uploadMedia(new File([], "a.png"))).rejects.toMatchObject({ status: 422 });
    const big = new File(["x"], "big.png", { type: "image/png" });
    Object.defineProperty(big, "size", { value: MAX_IMAGE_BYTES + 1 });
    await expect(uploadMedia(big)).rejects.toMatchObject({ status: 413 });
  });

  it("starts processing, reports progress and settles with the regions", async () => {
    const first = await uploadFile(image());
    expect(first).toMatchObject({ kind: "image", status: "processing", mode: "multimodal", attempt: 1 });
    expect(first.regions).toEqual([]);
    const seen: Snapshot[] = [];
    const done = await waitUntilSettled((s) => seen.push(s));
    expect(done.status).toBe("ready");
    expect(done.regions.map((r) => r.kind)).toEqual(["face", "identity_document", "plate"]);
    expect(seen.some((s) => s.status === "processing" && s.progress.completed > 0)).toBe(true);
    expect(mediaSourceUrl(done)).toMatch(/^data:image/);
    expect(mediaOutputUrl(done)).toBeNull();
  });

  it("saves edited regions, rejecting a stale attempt or a bad interval", async () => {
    await uploadMedia(image());
    const ready = await waitUntilSettled(() => {});
    const [first, ...rest] = ready.regions;
    const saved = await updateRegions(1, rest);
    expect(saved.regions).toHaveLength(2);
    await expect(updateRegions(9, rest)).rejects.toMatchObject({ status: 409 });
    await expect(updateRegions(1, [{ ...first!, start_ms: 5, end_ms: 1 }])).rejects.toMatchObject({ status: 422 });
    await expect(updateRegions(1, [{ ...first!, end_ms: 100 }])).rejects.toMatchObject({ status: 422 });
  });

  it("tracks a manual box through a video", async () => {
    await uploadMedia(video());
    const ready = await waitUntilSettled(() => {});
    expect(ready.kind).toBe("video");
    const manual = { ...ready.regions[0]!, source: "user" as const, start_ms: 1000, end_ms: 1000 };
    const tracked = await trackRegion(1, 1000, manual);
    expect(tracked.keyframes.length).toBeGreaterThan(1);
    expect(tracked.end_ms).toBe(ready.media.duration_ms);
    await expect(trackRegion(1, 99_999, manual)).rejects.toMatchObject({ status: 422 });
  });

  it("reject re-analyses with the next attempt and keeps the region count in the history", async () => {
    await uploadMedia(image());
    await waitUntilSettled(() => {});
    const next = await rejectVersion(1, "", "also hide the sign");
    expect(next).toMatchObject({ attempt: 2, status: "processing" });
    expect(next.history).toEqual([{ attempt: 1, text: "", reason: "also hide the sign", regions: 3 }]);
    expect((await waitUntilSettled(() => {})).status).toBe("ready");
  });

  it("approve exports in the background and then offers the download", async () => {
    await uploadMedia(image());
    await waitUntilSettled(() => {});
    const exporting = await approveVersion();
    expect(exporting.status).toBe("exporting");
    expect(exporting.approved).toBe(false);
    const done = await waitUntilSettled(() => {});
    expect(done).toMatchObject({ status: "ready", approved: true });
    expect(mediaOutputUrl(done)).not.toBeNull();
    expect((await getCurrent()).approved).toBe(true);
    // Editing the regions again withdraws the approval and the exported file.
    const edited = await updateRegions(done.attempt, done.regions.slice(1));
    expect(edited.approved).toBe(false);
    expect(mediaOutputUrl(edited)).toBeNull();
  });
});
