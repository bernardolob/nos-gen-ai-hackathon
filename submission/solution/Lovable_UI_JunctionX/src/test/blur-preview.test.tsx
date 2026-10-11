import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
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
    const toggle = screen.getByRole("button", { name: /hide blur/i });
    fireEvent.click(toggle);
    await waitFor(() => expect(screen.queryByTestId("blur-preview")).not.toBeInTheDocument());
    // The button says what the next click does.
    expect(toggle).toHaveTextContent(/show blur/i);
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

  it("hides the outlines and the labels while the blur is shown, except on the selected region", async () => {
    previewMedia.mockResolvedValue("blob:redacted");
    show(await readySnapshot("image"));
    await screen.findByTestId("blur-preview");
    const picture = screen.getByTestId("media-container");
    // Nothing is outlined or labelled over the picture...
    expect(within(picture).queryByText("Face")).not.toBeInTheDocument();
    expect(within(picture).queryByText("ID document")).not.toBeInTheDocument();
    expect(screen.getByTestId("box-r-face")).toHaveAttribute("data-outlined", "false");
    expect(screen.getByTestId("box-r-id")).toHaveAttribute("data-outlined", "false");
    // ...but a region can still be picked, and then it shows its outline and label.
    fireEvent.click(screen.getByTestId("box-r-face"));
    expect(within(picture).getByText("Face")).toBeInTheDocument();
    expect(screen.getByTestId("box-r-face")).toHaveAttribute("data-outlined", "true");
    expect(screen.getByTestId("box-r-id")).toHaveAttribute("data-outlined", "false");
    expect(within(picture).queryByText("ID document")).not.toBeInTheDocument();
  });

  it("shows every outline again when the blur preview is off", async () => {
    previewMedia.mockResolvedValue("blob:redacted");
    show(await readySnapshot("image"));
    await screen.findByTestId("blur-preview");
    fireEvent.click(screen.getByRole("button", { name: /hide blur|show blur/i }));
    await waitFor(() => expect(screen.queryByTestId("blur-preview")).not.toBeInTheDocument());
    const picture = screen.getByTestId("media-container");
    expect(within(picture).getByText("Face")).toBeInTheDocument();
    expect(within(picture).getByText("ID document")).toBeInTheDocument();
  });

  it("keeps the blur while a video plays, drawn live, and lets the button turn it off", async () => {
    // jsdom has no canvas: the live blur then just has nothing to draw on.
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
    previewMedia.mockResolvedValue("blob:frame");
    show(await readySnapshot("video"));
    await screen.findByTestId("blur-preview");
    const picture = screen.getByTestId("media-container");
    const video = picture.querySelector("video") as HTMLVideoElement;
    // Playing: the still frame gives way to the live blur, with no outlines.
    fireEvent.play(video);
    expect(await within(picture).findByTestId("live-blur")).toBeInTheDocument();
    expect(within(picture).queryByTestId("blur-preview")).not.toBeInTheDocument();
    expect(screen.getByTestId("box-r-face")).toHaveAttribute("data-outlined", "false");
    // The button hides it: outlines are back and so is the original.
    fireEvent.click(screen.getByRole("button", { name: /hide blur/i }));
    await waitFor(() => expect(within(picture).queryByTestId("live-blur")).not.toBeInTheDocument());
    expect(screen.getByTestId("box-r-face")).toHaveAttribute("data-outlined", "true");
    // Show it again and pause: the still frame comes back.
    fireEvent.click(screen.getByRole("button", { name: /show blur/i }));
    fireEvent.pause(video);
    expect(await within(picture).findByTestId("blur-preview")).toBeInTheDocument();
    expect(within(picture).queryByTestId("live-blur")).not.toBeInTheDocument();
  });
});
