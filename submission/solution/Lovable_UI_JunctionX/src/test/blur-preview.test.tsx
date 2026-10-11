import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Snapshot } from "@/lib/review/types";

// The preview is drawn by the backend, so these tests run as if it were real.
const previewMedia = vi.fn();
vi.mock("@/lib/review/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/review/api")>()),
  isMockMode: false,
  previewMedia: (...args: unknown[]) => previewMedia(...args),
}));

import { ReviewWorkspace } from "@/components/review/workspace";
import { mockUploadMedia, mockCurrent, resetMock } from "@/lib/review/mock";

async function readySnapshot(kind: "image" | "video"): Promise<Snapshot> {
  await mockUploadMedia(kind, kind === "image" ? "photo.jpg" : "clip.mp4");
  let snap = await mockCurrent();
  for (let i = 0; i < 6 && snap.status !== "ready"; i++) snap = await mockCurrent();
  return snap;
}

const show = (snapshot: Snapshot) =>
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

describe("Blur preview", () => {
  beforeEach(() => {
    resetMock();
    previewMedia.mockReset();
    URL.revokeObjectURL = vi.fn();
  });

  it("draws the redacted picture over the photo, with the regions of the draft", async () => {
    previewMedia.mockResolvedValue("blob:redacted");
    const snapshot = await readySnapshot("image");
    show(snapshot);
    const overlay = await screen.findByTestId("blur-preview");
    expect(overlay).toHaveAttribute("src", "blob:redacted");
    expect(previewMedia).toHaveBeenCalledWith(snapshot.attempt, 0, snapshot.regions);
  });

  it("hides it when the toggle is off, and shows it again", async () => {
    previewMedia.mockResolvedValue("blob:redacted");
    show(await readySnapshot("image"));
    await screen.findByTestId("blur-preview");
    const toggle = screen.getByRole("button", { name: /blur preview/i });
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(toggle);
    await waitFor(() => expect(screen.queryByTestId("blur-preview")).not.toBeInTheDocument());
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(await screen.findByTestId("blur-preview")).toBeInTheDocument();
  });

  it("for a video it asks for the frame at the current time", async () => {
    previewMedia.mockResolvedValue("blob:frame");
    const snapshot = await readySnapshot("video");
    show(snapshot);
    await screen.findByTestId("blur-preview");
    expect(previewMedia).toHaveBeenCalledWith(snapshot.attempt, 0, expect.any(Array));
  });

  it("says so, without breaking the review, when the preview cannot be drawn", async () => {
    previewMedia.mockRejectedValue(new Error("Não foi possível gerar a pré-visualização."));
    show(await readySnapshot("image"));
    expect(await screen.findByText(/Blur preview unavailable: Não foi possível/)).toBeInTheDocument();
    expect(screen.queryByTestId("blur-preview")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /approve version/i })).toBeEnabled();
  });
});
