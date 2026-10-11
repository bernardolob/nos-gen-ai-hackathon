import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReviewWorkspace } from "@/components/review/workspace";
import {
  getActiveKeyframe,
  getActiveRenderRegion,
  interpolateBox,
} from "@/components/review/media-review";
import { EMPTY_SNAPSHOT, type MediaRegion, type Snapshot } from "@/lib/review/types";

function createMediaSnapshot(overrides: Partial<Snapshot> = {}): Snapshot {
  return {
    ...EMPTY_SNAPSHOT,
    has_document: true,
    kind: "image",
    status: "ready",
    attempt: 1,
    media: {
      source_url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
      filename: "test-photo.jpg",
      width: 1920,
      height: 1080,
    },
    regions: [],
    ...overrides,
  };
}

describe("Media review UI (Request 2a)", () => {
  it("draws boxes positioned from keyframes using normalized percentages", () => {
    const region: MediaRegion = {
      id: "r-box-1",
      category: "identificacao",
      kind: "identity_document",
      reason: "ID card visible",
      confidence: "certo",
      source: "gemini",
      start_ms: 0,
      end_ms: 0,
      keyframes: [
        {
          time_ms: 0,
          box: { x: 0.15, y: 0.25, width: 0.35, height: 0.45 },
          polygon: null,
        },
      ],
    };

    const snapshot = createMediaSnapshot({
      regions: [region],
    });

    render(
      <ReviewWorkspace
        snapshot={snapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={async () => true}
        onApprove={() => {}}
        onNewDocument={() => {}}
      />,
    );

    const box = screen.getByTestId("box-r-box-1");
    expect(box).toBeInTheDocument();
    expect(box.style.left).toBe("15%");
    expect(box.style.top).toBe("25%");
    expect(box.style.width).toBe("35%");
    expect(box.style.height).toBe("45%");
    fireEvent.click(box);
    expect(box).toHaveTextContent("ID document");
    expect(screen.getByText("Regions")).toBeInTheDocument();
  });

  it("picks the right keyframe for video playback time and hides boxes outside the region duration", () => {
    const videoRegion: MediaRegion = {
      id: "r-video-face",
      category: "biometrico",
      kind: "face",
      reason: "Face in motion",
      confidence: "certo",
      source: "face_detector",
      start_ms: 500,
      end_ms: 3000,
      keyframes: [
        {
          time_ms: 500,
          box: { x: 0.1, y: 0.1, width: 0.2, height: 0.2 },
          polygon: null,
        },
        {
          time_ms: 1500,
          box: { x: 0.4, y: 0.1, width: 0.2, height: 0.2 },
          polygon: null,
        },
        {
          time_ms: 2500,
          box: { x: 0.7, y: 0.1, width: 0.2, height: 0.2 },
          polygon: null,
        },
      ],
    };

    // Before start_ms: not visible
    expect(getActiveKeyframe(videoRegion, 200, false)).toBeNull();

    // At 500ms exact: matches 500ms keyframe
    const kf1 = getActiveKeyframe(videoRegion, 500, false);
    expect(kf1?.box.x).toBe(0.1);

    // At 1500ms exact: matches 1500ms keyframe
    const kf2 = getActiveKeyframe(videoRegion, 1500, false);
    expect(kf2?.box.x).toBe(0.4);

    // At 2500ms exact: matches 2500ms keyframe
    const kf3 = getActiveKeyframe(videoRegion, 2500, false);
    expect(kf3?.box.x).toBe(0.7);

    // After end_ms: not visible
    expect(getActiveKeyframe(videoRegion, 3500, false)).toBeNull();
  });

  it("groups regions by category with human-readable titles in the right panel and updates selection", () => {
    const regions: MediaRegion[] = [
      {
        id: "r-1",
        category: "identificacao",
        kind: "identity_document",
        reason: "Tax card",
        confidence: "certo",
        source: "gemini",
        start_ms: 0,
        end_ms: 0,
        keyframes: [{ time_ms: 0, box: { x: 0.1, y: 0.1, width: 0.2, height: 0.2 }, polygon: null }],
      },
      {
        id: "r-2",
        category: "biometrico",
        kind: "face",
        reason: "Biometric face scan",
        confidence: "provavel",
        source: "face_detector",
        start_ms: 0,
        end_ms: 0,
        keyframes: [{ time_ms: 0, box: { x: 0.4, y: 0.1, width: 0.2, height: 0.2 }, polygon: null }],
      },
      {
        id: "r-3",
        category: "saude",
        kind: "text",
        reason: "Medical prescription",
        confidence: "incerto",
        source: "user",
        start_ms: 0,
        end_ms: 0,
        keyframes: [{ time_ms: 0, box: { x: 0.7, y: 0.1, width: 0.2, height: 0.2 }, polygon: null }],
      },
    ];

    const snapshot = createMediaSnapshot({ regions });

    render(
      <ReviewWorkspace
        snapshot={snapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={async () => true}
        onApprove={() => {}}
        onNewDocument={() => {}}
      />,
    );

    // Group headings
    expect(screen.getByText("Personal identification")).toBeInTheDocument();
    expect(screen.getByText("Biometric")).toBeInTheDocument();
    expect(screen.getByText("Health")).toBeInTheDocument();

    // Badges & details
    expect(screen.getByText("Certain")).toBeInTheDocument();
    expect(screen.getByText("Probable")).toBeInTheDocument();
    expect(screen.getByText("Uncertain")).toBeInTheDocument();
    expect(screen.getByText("Tax card")).toBeInTheDocument();
    expect(screen.getByText("Medical prescription")).toBeInTheDocument();

    // Selecting an item in the right panel selects it
    const item = screen.getByTestId("region-item-r-1");
    fireEvent.click(item);
    expect(item).toBeInTheDocument();
  });

  it("draws a polygon instead of the box when a polygon is present on the keyframe", () => {
    const polygonPoints = [
      { x: 0.2, y: 0.2 },
      { x: 0.4, y: 0.2 },
      { x: 0.35, y: 0.5 },
      { x: 0.25, y: 0.5 },
    ];

    const regionWithPoly: MediaRegion = {
      id: "r-poly",
      category: "biometrico",
      kind: "face",
      reason: "Face landmark mesh",
      confidence: "certo",
      source: "face_detector",
      start_ms: 0,
      end_ms: 0,
      keyframes: [
        {
          time_ms: 0,
          box: { x: 0.2, y: 0.2, width: 0.2, height: 0.3 },
          polygon: polygonPoints,
        },
      ],
    };

    const snapshot = createMediaSnapshot({
      regions: [regionWithPoly],
    });

    render(
      <ReviewWorkspace
        snapshot={snapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={async () => true}
        onApprove={() => {}}
        onNewDocument={() => {}}
      />,
    );

    const polygon = screen.getByTestId("polygon-r-poly");
    expect(polygon).toBeInTheDocument();
    expect(polygon.tagName.toLowerCase()).toBe("polygon");
    expect(polygon.getAttribute("points")).toBe("20,20 40,20 35,50 25,50");

    // The rectangular box div is NOT drawn
    expect(screen.queryByTestId("box-r-poly")).not.toBeInTheDocument();
  });
});

describe("Media review loop (Request 2b)", () => {
  it("interpolates the box linearly at the midpoint between two keyframes", () => {
    const box1 = { x: 0.1, y: 0.2, width: 0.2, height: 0.2 };
    const box2 = { x: 0.5, y: 0.6, width: 0.4, height: 0.4 };

    // Direct interpolateBox function at midpoint t=0.5
    const midBox = interpolateBox(box1, box2, 0.5);
    expect(midBox.x).toBeCloseTo(0.3);
    expect(midBox.y).toBeCloseTo(0.4);
    expect(midBox.width).toBeCloseTo(0.3);
    expect(midBox.height).toBeCloseTo(0.3);

    // Active keyframe interpolation inside region
    const region: MediaRegion = {
      id: "r-interp",
      category: "identificacao",
      kind: "plate",
      reason: "License plate moving",
      confidence: "certo",
      source: "gemini",
      start_ms: 0,
      end_ms: 2000,
      keyframes: [
        { time_ms: 0, box: box1, polygon: null },
        { time_ms: 1000, box: box2, polygon: null },
      ],
    };

    const renderedAt500 = getActiveRenderRegion(region, 500, false);
    expect(renderedAt500).not.toBeNull();
    expect(renderedAt500?.box.x).toBeCloseTo(0.3);
    expect(renderedAt500?.box.y).toBeCloseTo(0.4);
    expect(renderedAt500?.box.width).toBeCloseTo(0.3);
    expect(renderedAt500?.box.height).toBeCloseTo(0.3);
  });

  it("reject then approve ends with the Download button visible when approved with output_url", () => {
    const approvedSnapshot = createMediaSnapshot({
      attempt: 2,
      approved: true,
      status: "ready",
      media: {
        source_url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        output_url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        filename: "test-photo.jpg",
      },
    });

    render(
      <ReviewWorkspace
        snapshot={approvedSnapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={async () => true}
        onApprove={() => {}}
        onNewDocument={() => {}}
      />,
    );

    expect(screen.getByText("Version 2 approved.")).toBeInTheDocument();
    const downloadBtn = screen.getByRole("button", { name: /Download image/i });
    expect(downloadBtn).toBeInTheDocument();
  });

  it("failure of the export shows the alert and retry button", () => {
    const failedSnapshot = createMediaSnapshot({
      status: "failed",
      error: "Export failed due to image processing error",
    });

    const retryMock = vi.fn();

    render(
      <ReviewWorkspace
        snapshot={failedSnapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={retryMock}
        onReject={async () => true}
        onApprove={() => {}}
        onNewDocument={() => {}}
      />,
    );

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("Export failed due to image processing error")).toBeInTheDocument();

    const tryAgainBtn = screen.getByRole("button", { name: /Try again/i });
    expect(tryAgainBtn).toBeInTheDocument();
    fireEvent.click(tryAgainBtn);
    expect(retryMock).toHaveBeenCalledTimes(1);
  });

  it("the history sheet for media shows the region count instead of text preview", () => {
    const snapshotWithHistory = createMediaSnapshot({
      attempt: 2,
      history: [
        {
          attempt: 1,
          text: "",
          reason: "Hide the background face",
          regions: 3,
        },
      ],
    });

    render(
      <ReviewWorkspace
        snapshot={snapshotWithHistory}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={async () => true}
        onApprove={() => {}}
        onNewDocument={() => {}}
      />,
    );

    // Open the history sheet
    const historyBtn = screen.getByRole("button", { name: /History \(1\)/i });
    fireEvent.click(historyBtn);

    expect(screen.getByText("Attempt 1")).toBeInTheDocument();
    expect(screen.getByText("3 regions")).toBeInTheDocument();
    expect(screen.getByText(/Hide the background face/)).toBeInTheDocument();

    // Must NOT contain copy or download .txt buttons
    expect(screen.queryByRole("button", { name: /Download \.txt/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Copy/i })).not.toBeInTheDocument();
  });
  it('a video snapshot whose media.filename is "clip.mov" downloads as anonymized-video.mp4', async () => {
    const videoSnapshot = createMediaSnapshot({
      kind: "video",
      attempt: 1,
      approved: true,
      status: "ready",
      media: {
        source_url: "data:video/mp4;base64,AAAA",
        output_url: "https://example.com/api/media/output.mp4",
        filename: "clip.mov",
      },
    });

    const fakeBlob = new Blob(["fake video content"], { type: "video/mp4" });
    const originalFetch = globalThis.fetch;
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      blob: async () => fakeBlob,
    } as Response);

    URL.createObjectURL = vi.fn().mockReturnValue("blob:fake-url");
    URL.revokeObjectURL = vi.fn();

    let downloadedFilename = "";
    const originalClick = HTMLAnchorElement.prototype.click;
    HTMLAnchorElement.prototype.click = function (this: HTMLAnchorElement) {
      downloadedFilename = this.download;
    };

    try {
      render(
        <ReviewWorkspace
          snapshot={videoSnapshot}
          busy={false}
          busyMessage=""
          error={null}
          onRetry={null}
          onReject={async () => true}
          onApprove={() => {}}
          onNewDocument={() => {}}
        />,
      );

      const downloadBtn = screen.getByRole("button", { name: /Download video/i });
      await act(async () => {
        fireEvent.click(downloadBtn);
      });

      await vi.waitFor(() => {
        expect(downloadedFilename).toBe("anonymized-video.mp4");
      });
    } finally {
      globalThis.fetch = originalFetch;
      URL.createObjectURL = originalCreateObjectURL;
      URL.revokeObjectURL = originalRevokeObjectURL;
      HTMLAnchorElement.prototype.click = originalClick;
    }
  });

  it("reject button is disabled when approved for text and audio, but stays enabled for image and video", () => {
    // 1. Text snapshot when approved -> Reject is disabled
    const approvedTextSnapshot = {
      ...EMPTY_SNAPSHOT,
      has_document: true,
      kind: "text" as const,
      status: "ready" as const,
      attempt: 1,
      approved: true,
      text: "Masked text content",
    };

    const { rerender } = render(
      <ReviewWorkspace
        snapshot={approvedTextSnapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={async () => true}
        onApprove={() => {}}
        onNewDocument={() => {}}
      />,
    );

    const textRejectBtn = screen.getByRole("button", { name: /Reject/i });
    expect(textRejectBtn).toBeDisabled();

    // 2. Audio snapshot when approved -> Reject is disabled
    const approvedAudioSnapshot = {
      ...EMPTY_SNAPSHOT,
      has_document: true,
      kind: "audio" as const,
      status: "ready" as const,
      attempt: 1,
      approved: true,
      text: "Masked audio transcript",
      audio_url: "data:audio/wav;base64,AAAA",
    };

    rerender(
      <ReviewWorkspace
        snapshot={approvedAudioSnapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={async () => true}
        onApprove={() => {}}
        onNewDocument={() => {}}
      />,
    );

    const audioRejectBtn = screen.getByRole("button", { name: /Reject/i });
    expect(audioRejectBtn).toBeDisabled();

    // 3. Image snapshot when approved -> Reject is enabled
    const approvedImageSnapshot = createMediaSnapshot({
      kind: "image",
      attempt: 1,
      approved: true,
      status: "ready",
    });

    rerender(
      <ReviewWorkspace
        snapshot={approvedImageSnapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={async () => true}
        onApprove={() => {}}
        onNewDocument={() => {}}
      />,
    );

    const imageRejectBtn = screen.getByRole("button", { name: /Reject/i });
    expect(imageRejectBtn).toBeEnabled();

    // 4. Video snapshot when approved -> Reject is enabled
    const approvedVideoSnapshot = createMediaSnapshot({
      kind: "video",
      attempt: 1,
      approved: true,
      status: "ready",
    });

    rerender(
      <ReviewWorkspace
        snapshot={approvedVideoSnapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={async () => true}
        onApprove={() => {}}
        onNewDocument={() => {}}
      />,
    );

    const videoRejectBtn = screen.getByRole("button", { name: /Reject/i });
    expect(videoRejectBtn).toBeEnabled();
  });
});
