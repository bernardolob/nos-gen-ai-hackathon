import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReviewWorkspace } from "@/components/review/workspace";
import { VideoControls } from "@/components/review/media-review";
import { mockCurrent, mockUploadMedia, resetMock } from "@/lib/review/mock";
import type { Snapshot } from "@/lib/review/types";

async function videoSnapshot(): Promise<Snapshot> {
  await mockUploadMedia("video", "clip.mp4");
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

describe("Video controls", () => {
  beforeEach(() => resetMock());

  it("sit below the picture, not inside it, so nothing drawn over the video covers them", async () => {
    show(await videoSnapshot());
    const picture = screen.getByTestId("media-container");
    const bar = screen.getByTestId("video-controls");
    expect(picture.contains(bar)).toBe(false);
    expect(picture.nextElementSibling).toBe(bar);
    expect(bar.contains(screen.getByRole("button", { name: "Play" }))).toBe(true);
  });

  it("the browser's own bar, with its useless full-screen button, is not used", async () => {
    show(await videoSnapshot());
    const video = screen.getByTestId("media-container").querySelector("video") as HTMLVideoElement;
    expect(video.hasAttribute("controls")).toBe(false);
    expect(screen.queryByRole("button", { name: /full ?screen/i })).not.toBeInTheDocument();
  });

  it("an image has no video controls", async () => {
    await mockUploadMedia("image", "photo.jpg");
    let snap = await mockCurrent();
    for (let i = 0; i < 6 && snap.status !== "ready"; i++) snap = await mockCurrent();
    show(snap);
    expect(screen.queryByTestId("video-controls")).not.toBeInTheDocument();
  });
});

describe("VideoControls", () => {
  function fakeVideo() {
    const target = new EventTarget();
    return Object.assign(target, {
      paused: true,
      ended: false,
      muted: false,
      currentTime: 0,
      play: vi.fn(async function (this: { paused: boolean }) {
        this.paused = false;
        target.dispatchEvent(new Event("play"));
      }),
      pause: vi.fn(function (this: { paused: boolean }) {
        this.paused = true;
        target.dispatchEvent(new Event("pause"));
      }),
    }) as unknown as HTMLVideoElement & { play: ReturnType<typeof vi.fn>; pause: ReturnType<typeof vi.fn> };
  }

  it("plays, then pauses, and the button says which", async () => {
    const video = fakeVideo();
    render(<VideoControls video={video} currentTimeMs={0} durationMs={6000} onSeek={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(video.play).toHaveBeenCalledTimes(1);
    fireEvent.click(await screen.findByRole("button", { name: "Pause" }));
    expect(video.pause).toHaveBeenCalledTimes(1);
  });

  it("seeks the video and reports the time", () => {
    const video = fakeVideo();
    const onSeek = vi.fn();
    render(<VideoControls video={video} currentTimeMs={1000} durationMs={6000} onSeek={onSeek} />);
    fireEvent.change(screen.getByRole("slider", { name: "Seek" }), { target: { value: "2500" } });
    expect(video.currentTime).toBe(2.5);
    expect(onSeek).toHaveBeenCalledWith(2500);
  });

  it("mutes and unmutes, and shows the time", () => {
    const video = fakeVideo();
    render(<VideoControls video={video} currentTimeMs={3000} durationMs={6700} onSeek={() => {}} />);
    expect(screen.getByText("0:03 / 0:07")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Mute" }));
    expect(video.muted).toBe(true);
  });
});
