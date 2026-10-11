import { render, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UploadStep } from "@/components/anonymizer/steps";
import { useAudioOnly } from "@/lib/use-audio-only";

/** A <video> whose metadata says it has this picture size (0 = no picture). */
function fakeVideo(width: number, height: number) {
  const real = document.createElement.bind(document);
  vi.spyOn(document, "createElement").mockImplementation(((tag: string, options?: ElementCreationOptions) => {
    if (tag !== "video") return real(tag, options);
    const video = {
      preload: "",
      muted: false,
      videoWidth: width,
      videoHeight: height,
      onloadedmetadata: null as null | (() => void),
      removeAttribute: () => {},
      set src(_value: string) {
        queueMicrotask(() => video.onloadedmetadata?.());
      },
    };
    return video as unknown as HTMLVideoElement;
  }) as typeof document.createElement);
}

const recording = () => new File(["x"], "Voice note.m4a.mp4", { type: "video/mp4" });

describe("A voice recording saved as .mp4", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is recognised as audio when the file has no picture", async () => {
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    fakeVideo(0, 0);
    const { result } = renderHook(() => useAudioOnly(recording()));
    await waitFor(() => expect(result.current).toBe(true));
  });

  it("stays a video when the file has a picture", async () => {
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
    fakeVideo(1280, 720);
    const file = recording();
    const { result } = renderHook(() => useAudioOnly(file));
    await new Promise((r) => setTimeout(r, 20));
    expect(result.current).toBe(false);
  });

  it("is never audio for a photo, a document or no file", () => {
    expect(renderHook(() => useAudioOnly(null)).result.current).toBe(false);
    const photo = new File(["x"], "a.png", { type: "image/png" });
    expect(renderHook(() => useAudioOnly(photo)).result.current).toBe(false);
  });

  it("shows the audio notice (ElevenLabs), not the video one (Gemini)", () => {
    render(
      <UploadStep
        file={recording()}
        onFile={() => {}}
        onAnalyze={() => {}}
        loading={false}
        status=""
        error={null}
        onRetry={() => {}}
        audioEnabled
        audioOnly
      />,
    );
    expect(screen.getByText(/sent to a third-party service \(ElevenLabs\)/i)).toBeInTheDocument();
    expect(screen.queryByText(/Sampled frames are sent/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Audio up to 25 MB/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /analyze document/i })).toBeDisabled();
  });

  it("with the picture it keeps the video notice", () => {
    render(
      <UploadStep
        file={recording()}
        onFile={() => {}}
        onAnalyze={() => {}}
        loading={false}
        status=""
        error={null}
        onRetry={() => {}}
        audioEnabled
      />,
    );
    expect(screen.getByText(/Sampled frames are sent/i)).toBeInTheDocument();
    expect(screen.queryByText(/ElevenLabs/i)).not.toBeInTheDocument();
  });
});
