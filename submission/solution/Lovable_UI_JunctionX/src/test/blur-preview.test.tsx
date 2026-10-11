import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MediaRegion, Snapshot } from "@/lib/review/types";
import { EMPTY_SNAPSHOT } from "@/lib/review/types";
import { MediaViewer } from "@/components/review/media-review";
import { ReviewWorkspace } from "@/components/review/workspace";
import { createPixelatedPreview, getActiveRenderRegion } from "@/lib/review/media-preview";

const previewMedia = vi.fn();
vi.mock("@/lib/review/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/review/api")>()),
  previewMedia: (...args: unknown[]) => previewMedia(...args),
}));

const region: MediaRegion = {
  id: "face",
  kind: "face",
  source: "face_detector",
  category: "biometrico",
  reason: "A visible face",
  confidence: "certo",
  start_ms: 0,
  end_ms: 1000,
  keyframes: [
    { time_ms: 0, polygon: null, box: { x: 0.1, y: 0.1, width: 0.3, height: 0.2 } },
    { time_ms: 1000, polygon: null, box: { x: 0.5, y: 0.5, width: 0.3, height: 0.2 } },
  ],
};

function snapshot(kind: "image" | "video" = "image", attempt = 1): Snapshot {
  return {
    ...EMPTY_SNAPSHOT,
    kind,
    attempt,
    status: "ready",
    has_document: true,
    media: {
      source_url: "data:image/png;base64,test",
      filename: "media",
      width: 100,
      height: 80,
      duration_ms: 1000,
    },
    regions: [region],
  };
}

type Context = ReturnType<typeof context>;
function context() {
  return {
    clearRect: vi.fn(),
    drawImage: vi.fn(),
    fillRect: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    closePath: vi.fn(),
    clip: vi.fn(),
    imageSmoothingEnabled: true,
    imageSmoothingQuality: "low",
    fillStyle: "",
  };
}
let contexts: Map<HTMLCanvasElement, Context>;
beforeEach(() => {
  contexts = new Map();
  previewMedia.mockReset();
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(function (
    this: HTMLCanvasElement,
  ) {
    if (!contexts.has(this)) contexts.set(this, context());
    return contexts.get(this) as unknown as CanvasRenderingContext2D;
  });
});
afterEach(() => vi.restoreAllMocks());

function showWorkspace(snap = snapshot()) {
  return render(
    <ReviewWorkspace
      snapshot={snap}
      busy={false}
      busyMessage=""
      error={null}
      onRetry={null}
      onReject={async () => true}
      onApprove={() => {}}
      onNewDocument={() => {}}
    />,
  );
}
function loadImage() {
  const image = within(screen.getByTestId("media-container")).getByRole("img") as HTMLImageElement;
  Object.defineProperties(image, {
    naturalWidth: { configurable: true, value: 100 },
    naturalHeight: { configurable: true, value: 80 },
  });
  fireEvent.load(image);
  return image;
}
function viewer(snap: Snapshot, props: Partial<React.ComponentProps<typeof MediaViewer>> = {}) {
  return (
    <MediaViewer
      snapshot={snap}
      currentTimeMs={0}
      onTimeUpdate={() => {}}
      selectedRegionId={null}
      onSelectRegion={() => {}}
      previewEnabled
      {...props}
    />
  );
}
function loadVideo(video: HTMLVideoElement) {
  Object.defineProperties(video, {
    videoWidth: { configurable: true, value: 100 },
    videoHeight: { configurable: true, value: 80 },
    readyState: { configurable: true, value: 2 },
  });
  fireEvent.loadedData(video);
}
function previewContext() {
  return contexts.get(screen.getByTestId("censorship-preview") as HTMLCanvasElement)!;
}

describe("Live censorship preview", () => {
  it("paints faces with opaque mosaic cells and tint without requesting the backend", () => {
    showWorkspace();
    const image = loadImage();
    expect(image).toHaveAttribute("crossorigin", "anonymous");
    const canvas = screen.getByTestId("censorship-preview") as HTMLCanvasElement;
    expect(canvas).toBeVisible();
    expect([canvas.width, canvas.height]).toEqual([100, 80]);
    expect(previewContext().drawImage).toHaveBeenCalledWith(
      expect.any(HTMLCanvasElement),
      10,
      8,
      30,
      16,
    );
    expect(previewContext().fillRect).toHaveBeenCalledWith(10, 8, 30, 16);
    expect(previewContext().fillStyle).toBe("rgba(43, 69, 90, 0.22)");
    expect(previewContext().imageSmoothingEnabled).toBe(false);
    const coarse = [...contexts.keys()].find((item) => item.width === 2 && item.height === 1)!;
    expect(contexts.get(coarse)!.drawImage).toHaveBeenCalledWith(
      expect.any(HTMLCanvasElement),
      10,
      8,
      30,
      16,
      0,
      0,
      2,
      1,
    );
    expect(previewMedia).not.toHaveBeenCalled();
  });

  it("keeps the toggle enabled by default and restores outlines when switched off", () => {
    showWorkspace();
    loadImage();
    const toggle = screen.getByRole("button", { name: /censorship preview/i });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("box-face")).toHaveAttribute("data-outlined", "false");
    fireEvent.click(screen.getByTestId("box-face"));
    expect(screen.getByTestId("box-face")).toHaveAttribute("data-outlined", "true");
    fireEvent.click(toggle);
    expect(screen.getByTestId("censorship-preview")).not.toBeVisible();
    expect(screen.getByTestId("box-face")).toHaveAttribute("data-outlined", "true");
    fireEvent.click(toggle);
    expect(screen.getByTestId("censorship-preview")).toBeVisible();
  });

  it("immediately redraws unsaved edits and reuses its canvases", () => {
    const snap = snapshot();
    const { rerender } = render(viewer(snap));
    loadImage();
    const allocated = [...contexts.keys()];
    const edited = {
      ...region,
      keyframes: [{ time_ms: 0, polygon: null, box: { x: 0.6, y: 0.5, width: 0.2, height: 0.3 } }],
    };
    rerender(viewer(snap, { regions: [edited] }));
    expect(previewContext().fillRect).toHaveBeenLastCalledWith(60, 40, 20, 24);
    expect([...contexts.keys()]).toEqual(allocated);
    expect(previewMedia).not.toHaveBeenCalled();
  });

  it("clips polygon regions and restores the context even on drawing errors", () => {
    const renderer = createPixelatedPreview();
    const canvas = document.createElement("canvas");
    const polygon = [
      { x: 0.1, y: 0.1 },
      { x: 0.4, y: 0.1 },
      { x: 0.2, y: 0.3 },
    ];
    const item = { ...region, keyframes: [{ ...region.keyframes[0]!, polygon }] };
    renderer(canvas, document.createElement("img"), [item], 0, 100, 80, true);
    const ctx = contexts.get(canvas)!;
    expect(ctx.moveTo).toHaveBeenCalledWith(10, 8);
    expect(ctx.clip).toHaveBeenCalledOnce();
    ctx.drawImage.mockImplementationOnce(() => {
      throw new Error("draw failed");
    });
    expect(() =>
      renderer(canvas, document.createElement("img"), [item], 0, 100, 80, true),
    ).toThrow();
    expect(ctx.restore).toHaveBeenCalledTimes(2);
  });

  it("uses solid masks on canvas failure and preserves editing", () => {
    vi.mocked(HTMLCanvasElement.prototype.getContext).mockReturnValue(null);
    showWorkspace();
    loadImage();
    expect(screen.getByText(/Censorship preview unavailable:/)).toBeInTheDocument();
    expect(screen.getByTestId("censorship-fallback").querySelector("rect")).toHaveAttribute(
      "fill",
      "rgb(43, 69, 90)",
    );
    expect(screen.getByTestId("censorship-preview")).not.toBeVisible();
    fireEvent.click(screen.getByTestId("box-face"));
    expect(screen.getByTestId("box-face")).toHaveAttribute("data-outlined", "true");
  });

  it("reports media load errors and clears stale output on a new attempt", () => {
    const error = vi.fn();
    const { rerender } = render(viewer(snapshot(), { onPreviewError: error }));
    const image = loadImage();
    fireEvent.error(image);
    expect(error).toHaveBeenLastCalledWith(expect.stringContaining("Could not load"));
    rerender(viewer(snapshot("image", 2), { onPreviewError: error }));
    expect(screen.getByTestId("censorship-preview")).not.toBeVisible();
    expect(screen.getByTestId("censorship-fallback")).toBeInTheDocument();
    expect(error).toHaveBeenLastCalledWith(null);
    loadImage();
    expect(screen.getByTestId("censorship-preview")).toBeVisible();
  });

  it("paints each decoded frame at metadata.mediaTime and cancels callbacks", () => {
    const callbacks = new Map<number, VideoFrameRequestCallback>();
    let handle = 0;
    const request = vi.fn((callback: VideoFrameRequestCallback) => {
      callbacks.set(++handle, callback);
      return handle;
    });
    const cancel = vi.fn();
    const time = vi.fn();
    const ref = createRef<HTMLVideoElement>();
    const { unmount, rerender } = render(
      viewer(snapshot("video"), { videoRef: ref, onTimeUpdate: time }),
    );
    const video = ref.current!;
    Object.defineProperties(video, {
      paused: { configurable: true, value: false },
      requestVideoFrameCallback: { configurable: true, value: request },
      cancelVideoFrameCallback: { configurable: true, value: cancel },
    });
    loadVideo(video);
    act(() => callbacks.get(1)!(0, { mediaTime: 0.5 } as VideoFrameCallbackMetadata));
    expect(time).toHaveBeenLastCalledWith(500);
    expect(previewContext().fillRect).toHaveBeenLastCalledWith(30, 24, 30, 16);
    expect(screen.getByTestId("censorship-preview")).toBeVisible();
    const edited = {
      ...region,
      keyframes: [{ time_ms: 0, polygon: null, box: { x: 0.6, y: 0.5, width: 0.2, height: 0.3 } }],
    };
    rerender(viewer(snapshot("video"), { videoRef: ref, onTimeUpdate: time, regions: [edited] }));
    act(() => callbacks.get(2)!(0, { mediaTime: 0.7 } as VideoFrameCallbackMetadata));
    expect(previewContext().fillRect).toHaveBeenLastCalledWith(60, 40, 20, 24);
    expect(video).toHaveAttribute("controls");
    expect(video).toHaveAttribute("crossorigin", "anonymous");
    unmount();
    expect(cancel).toHaveBeenLastCalledWith(3);
    act(() => callbacks.get(3)!(0, { mediaTime: 0.9 } as VideoFrameCallbackMetadata));
    expect(time).toHaveBeenLastCalledWith(700);
    expect(previewMedia).not.toHaveBeenCalled();
  });

  it("supports animation frame fallback, seek, pause and playback end", () => {
    let callback: FrameRequestCallback;
    vi.spyOn(window, "requestAnimationFrame").mockImplementation((fn) => {
      callback = fn;
      return 42;
    });
    const cancel = vi.spyOn(window, "cancelAnimationFrame").mockImplementation(() => {});
    const ref = createRef<HTMLVideoElement>();
    const { unmount } = render(viewer(snapshot("video"), { videoRef: ref }));
    const video = ref.current!;
    Object.defineProperties(video, {
      paused: { configurable: true, value: false },
      requestVideoFrameCallback: { configurable: true, value: undefined },
    });
    loadVideo(video);
    video.currentTime = 0.5;
    act(() => callback!(0));
    expect(previewContext().fillRect).toHaveBeenLastCalledWith(30, 24, 30, 16);
    fireEvent.seeking(video);
    expect(screen.getByTestId("censorship-fallback")).toBeInTheDocument();
    video.currentTime = 1;
    fireEvent.seeked(video);
    expect(previewContext().fillRect).toHaveBeenLastCalledWith(50, 40, 30, 16);
    fireEvent.pause(video);
    expect(cancel).toHaveBeenCalledWith(42);
    fireEvent.ended(video);
    expect(screen.getByTestId("censorship-preview")).toBeVisible();
    unmount();
  });

  it("clears regions outside their interval and at a source change", () => {
    const ref = createRef<HTMLVideoElement>();
    const snap = snapshot("video");
    const { rerender } = render(viewer(snap, { videoRef: ref }));
    loadVideo(ref.current!);
    const ctx = previewContext();
    ctx.fillRect.mockClear();
    rerender(viewer(snap, { videoRef: ref, currentTimeMs: 1001 }));
    expect(ctx.clearRect).toHaveBeenCalled();
    expect(ctx.fillRect).not.toHaveBeenCalled();
    rerender(viewer(snapshot("video", 2), { videoRef: ref }));
    expect(screen.getByTestId("censorship-preview")).not.toBeVisible();
  });
});

describe("Preview/export geometry", () => {
  it("uses the box between missing or incompatible polygons, and the exact polygon at anchors", () => {
    const polygon = [
      { x: 0.1, y: 0.1 },
      { x: 0.4, y: 0.1 },
      { x: 0.2, y: 0.3 },
    ];
    const first = { ...region.keyframes[0]!, polygon };
    for (const next of [null, polygon.slice(0, 2)]) {
      const item = { ...region, keyframes: [first, { ...region.keyframes[1]!, polygon: next }] };
      expect(getActiveRenderRegion(item, 0, false)!.polygon).toEqual(polygon);
      expect(getActiveRenderRegion(item, 500, false)!.polygon).toBeNull();
      expect(getActiveRenderRegion(item, 500, false)!.box.x).toBeCloseTo(0.3);
    }
  });

  it("interpolates matching vertices, handles unsorted keys and includes the end time", () => {
    const polygon = [
      { x: 0.1, y: 0.1 },
      { x: 0.4, y: 0.1 },
      { x: 0.2, y: 0.3 },
    ];
    const last = polygon.map((p) => ({ x: p.x + 0.4, y: p.y + 0.4 }));
    const item = {
      ...region,
      keyframes: [
        { ...region.keyframes[1]!, polygon: last },
        { ...region.keyframes[0]!, polygon },
      ],
    };
    expect(getActiveRenderRegion(item, 500, false)!.polygon![0]!.x).toBeCloseTo(0.3);
    expect(getActiveRenderRegion(item, 1000, false)!.polygon).toEqual(last);
    expect(getActiveRenderRegion(item, 1001, false)).toBeNull();
  });
});
