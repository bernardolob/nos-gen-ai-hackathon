import { render, screen, fireEvent, act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import { ReviewWorkspace } from "@/components/review/workspace";
import { updateRegionBoxAtTime } from "@/components/review/media-review";
import * as reviewApi from "@/lib/review/api";
import { ApiError } from "@/lib/review/types";
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

class CustomPointerEvent extends MouseEvent {
  constructor(type: string, init?: any) {
    super(type, init);
    if (init && "clientX" in init) {
      Object.defineProperty(this, "clientX", { value: init.clientX });
    }
    if (init && "clientY" in init) {
      Object.defineProperty(this, "clientY", { value: init.clientY });
    }
  }
}

describe("Media region editing (Request 2c)", () => {
  let origPointerEvent: any;

  beforeEach(() => {
    origPointerEvent = (globalThis as any).PointerEvent;
    (globalThis as any).PointerEvent = CustomPointerEvent;
    (window as any).PointerEvent = CustomPointerEvent;

    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      left: 0,
      top: 0,
      width: 1000,
      height: 1000,
      right: 1000,
      bottom: 1000,
      x: 0,
      y: 0,
      toJSON: () => {},
    });
  });

  afterEach(() => {
    (globalThis as any).PointerEvent = origPointerEvent;
    (window as any).PointerEvent = origPointerEvent;
    vi.restoreAllMocks();
  });

  it("drawing adds a region with source 'user'", async () => {
    const snapshot = createMediaSnapshot({
      regions: [],
    });

    render(
      <ReviewWorkspace
        snapshot={snapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={vi.fn().mockResolvedValue(true)}
        onApprove={vi.fn()}
        onNewDocument={vi.fn()}
      />
    );

    // Click "Add region" to enter drawing mode
    const addBtn = screen.getByRole("button", { name: /Add region/i });
    fireEvent.click(addBtn);

    const container = screen.getByTestId("media-container");

    // Pointer events for drawing: start at (100, 100) and drag to (300, 300)
    act(() => {
      fireEvent.pointerDown(container, { clientX: 100, clientY: 100 });
      fireEvent.pointerMove(window, { clientX: 300, clientY: 300 });
      fireEvent.pointerUp(window, { clientX: 300, clientY: 300 });
    });

    // The new region should have source "user" which renders as "You"
    expect(screen.getByText("You")).toBeInTheDocument();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save changes/i })).toBeInTheDocument();
  });

  it("moving a box clamps at the edges", async () => {
    const region: MediaRegion = {
      id: "r-move",
      category: "identificacao",
      kind: "face",
      reason: "Face visible",
      confidence: "certo",
      source: "gemini",
      start_ms: 0,
      end_ms: 0,
      keyframes: [
        {
          time_ms: 0,
          box: { x: 0.1, y: 0.1, width: 0.2, height: 0.2 },
          polygon: null,
        },
      ],
    };

    const snapshot = createMediaSnapshot({ regions: [region] });

    render(
      <ReviewWorkspace
        snapshot={snapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={vi.fn().mockResolvedValue(true)}
        onApprove={vi.fn()}
        onNewDocument={vi.fn()}
      />
    );

    const box = screen.getByTestId("box-r-move");

    // Drag beyond top-left boundary (negative client coords)
    act(() => {
      fireEvent.pointerDown(box, { clientX: 100, clientY: 100 });
      fireEvent.pointerMove(window, { clientX: -500, clientY: -500 });
      fireEvent.pointerUp(window);
    });

    expect(box.style.left).toBe("0%");
    expect(box.style.top).toBe("0%");

    // Drag beyond bottom-right boundary (large client coords)
    act(() => {
      fireEvent.pointerDown(box, { clientX: 0, clientY: 0 });
      fireEvent.pointerMove(window, { clientX: 2000, clientY: 2000 });
      fireEvent.pointerUp(window);
    });

    // width is 20%, so max left is 100% - 20% = 80%
    expect(box.style.left).toBe("80%");
    expect(box.style.top).toBe("80%");
  });

  it("editing a video box at t=1000 adds/replaces the keyframe at 1000", () => {
    const videoRegion: MediaRegion = {
      id: "r-video",
      category: "identificacao",
      kind: "face",
      reason: "Face",
      confidence: "certo",
      source: "gemini",
      start_ms: 0,
      end_ms: 3000,
      keyframes: [
        { time_ms: 0, box: { x: 0.1, y: 0.1, width: 0.1, height: 0.1 }, polygon: null },
        { time_ms: 2000, box: { x: 0.3, y: 0.3, width: 0.1, height: 0.1 }, polygon: null },
      ],
    };

    // Edit at t=1000 (adds keyframe)
    const updated = updateRegionBoxAtTime(
      videoRegion,
      { x: 0.2, y: 0.2, width: 0.15, height: 0.15 },
      1000,
      false
    );

    expect(updated.keyframes).toHaveLength(3);
    expect(updated.keyframes[1]).toEqual({
      time_ms: 1000,
      box: { x: 0.2, y: 0.2, width: 0.15, height: 0.15 },
      polygon: null,
    });
    expect(updated.keyframes[0]?.time_ms).toBe(0);
    expect(updated.keyframes[2]?.time_ms).toBe(2000);

    // Edit again at t=1000 (replaces keyframe)
    const replaced = updateRegionBoxAtTime(
      updated,
      { x: 0.25, y: 0.25, width: 0.18, height: 0.18 },
      1000,
      false
    );

    expect(replaced.keyframes).toHaveLength(3);
    expect(replaced.keyframes[1]?.box).toEqual({ x: 0.25, y: 0.25, width: 0.18, height: 0.18 });
  });

  it("saving calls updateRegions with the draft and the snapshot's attempt", async () => {
    const region: MediaRegion = {
      id: "r-save",
      category: "identificacao",
      kind: "face",
      reason: "Face",
      confidence: "certo",
      source: "gemini",
      start_ms: 0,
      end_ms: 0,
      keyframes: [
        { time_ms: 0, box: { x: 0.1, y: 0.1, width: 0.1, height: 0.1 }, polygon: null },
      ],
    };

    const snapshot = createMediaSnapshot({
      attempt: 3,
      regions: [region],
    });

    const updateRegionsSpy = vi.spyOn(reviewApi, "updateRegions").mockResolvedValue({
      ...snapshot,
      approved: false,
      regions: [],
    });

    render(
      <ReviewWorkspace
        snapshot={snapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={vi.fn().mockResolvedValue(true)}
        onApprove={vi.fn()}
        onNewDocument={vi.fn()}
      />
    );

    // Remove the region to dirty the draft
    const removeBtn = screen.getByRole("button", { name: "Remove region" });
    fireEvent.click(removeBtn);

    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

    const saveBtn = screen.getByRole("button", { name: /Save changes/i });
    await act(async () => {
      fireEvent.click(saveBtn);
    });

    expect(updateRegionsSpy).toHaveBeenCalledWith(3, []);
  });

  it("a stale attempt (409) shows the message", async () => {
    const region: MediaRegion = {
      id: "r-409",
      category: "identificacao",
      kind: "face",
      reason: "Face",
      confidence: "certo",
      source: "gemini",
      start_ms: 0,
      end_ms: 0,
      keyframes: [
        { time_ms: 0, box: { x: 0.1, y: 0.1, width: 0.1, height: 0.1 }, polygon: null },
      ],
    };

    const snapshot = createMediaSnapshot({
      attempt: 1,
      regions: [region],
    });

    vi.spyOn(reviewApi, "updateRegions").mockRejectedValue(
      new ApiError(409, "The version under review has already changed.")
    );
    vi.spyOn(reviewApi, "getCurrent").mockResolvedValue(snapshot);

    render(
      <ReviewWorkspace
        snapshot={snapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={vi.fn().mockResolvedValue(true)}
        onApprove={vi.fn()}
        onNewDocument={vi.fn()}
      />
    );

    // Remove region to create dirty draft
    fireEvent.click(screen.getByRole("button", { name: "Remove region" }));

    const saveBtn = screen.getByRole("button", { name: /Save changes/i });
    await act(async () => {
      fireEvent.click(saveBtn);
    });

    expect(
      await screen.findByText(/The version under review has/i)
    ).toBeInTheDocument();
  });

  it("Approve is disabled with unsaved changes", () => {
    const region: MediaRegion = {
      id: "r-approve",
      category: "identificacao",
      kind: "face",
      reason: "Face",
      confidence: "certo",
      source: "gemini",
      start_ms: 0,
      end_ms: 0,
      keyframes: [
        { time_ms: 0, box: { x: 0.1, y: 0.1, width: 0.1, height: 0.1 }, polygon: null },
      ],
    };

    const snapshot = createMediaSnapshot({
      approved: false,
      regions: [region],
    });

    render(
      <ReviewWorkspace
        snapshot={snapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={vi.fn().mockResolvedValue(true)}
        onApprove={vi.fn()}
        onNewDocument={vi.fn()}
      />
    );

    const approveBtn = screen.getByRole("button", { name: /Approve version/i });
    const rejectBtn = screen.getByRole("button", { name: /Reject/i });

    // Initially enabled (not dirty)
    expect(approveBtn).not.toBeDisabled();
    expect(rejectBtn).not.toBeDisabled();

    // Remove region -> dirty
    fireEvent.click(screen.getByRole("button", { name: "Remove region" }));

    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(approveBtn).toBeDisabled();
    expect(approveBtn).toHaveAttribute("title", "Save or discard your changes first");
    expect(rejectBtn).toBeDisabled();
    expect(rejectBtn).toHaveAttribute("title", "Save or discard your changes first");
  });

  it("Track replaces the region", async () => {
    const videoRegion: MediaRegion = {
      id: "r-track",
      category: "identificacao",
      kind: "face",
      reason: "Face",
      confidence: "certo",
      source: "gemini",
      start_ms: 500,
      end_ms: 1000,
      keyframes: [
        { time_ms: 500, box: { x: 0.2, y: 0.2, width: 0.1, height: 0.1 }, polygon: null },
      ],
    };

    const snapshot = createMediaSnapshot({
      kind: "video",
      attempt: 2,
      media: {
        source_url: "data:video/mp4;base64,AAAA",
        filename: "clip.mp4",
        width: 1280,
        height: 720,
        duration_ms: 5000,
      },
      regions: [videoRegion],
    });

    const trackedResult: MediaRegion = {
      ...videoRegion,
      start_ms: 0,
      end_ms: 5000,
      keyframes: [
        { time_ms: 0, box: { x: 0.2, y: 0.2, width: 0.1, height: 0.1 }, polygon: null },
        { time_ms: 2500, box: { x: 0.25, y: 0.25, width: 0.1, height: 0.1 }, polygon: null },
        { time_ms: 5000, box: { x: 0.3, y: 0.3, width: 0.1, height: 0.1 }, polygon: null },
      ],
    };

    const trackSpy = vi.spyOn(reviewApi, "trackRegion").mockResolvedValue(trackedResult);

    render(
      <ReviewWorkspace
        snapshot={snapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={vi.fn().mockResolvedValue(true)}
        onApprove={vi.fn()}
        onNewDocument={vi.fn()}
      />
    );

    const trackBtn = screen.getByRole("button", { name: "Track" });
    expect(trackBtn).toHaveAttribute(
      "title",
      "Follows the box forwards and backwards from the current frame"
    );

    await act(async () => {
      fireEvent.click(trackBtn);
    });

    expect(trackSpy).toHaveBeenCalledWith(2, 0, expect.objectContaining({ id: "r-track" }));
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });
});
