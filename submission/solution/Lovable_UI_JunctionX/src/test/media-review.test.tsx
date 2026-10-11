import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReviewWorkspace } from "@/components/review/workspace";
import { getActiveKeyframe } from "@/components/review/media-review";
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

    // At 800ms: picks 500ms keyframe
    const kf1 = getActiveKeyframe(videoRegion, 800, false);
    expect(kf1?.box.x).toBe(0.1);

    // At 1800ms: picks 1500ms keyframe
    const kf2 = getActiveKeyframe(videoRegion, 1800, false);
    expect(kf2?.box.x).toBe(0.4);

    // At 2900ms: picks 2500ms keyframe
    const kf3 = getActiveKeyframe(videoRegion, 2900, false);
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
    expect(item.className).toContain("border-primary");
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
