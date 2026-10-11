import { render, screen, fireEvent } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { UploadStep } from "@/components/anonymizer/steps";
import { ReviewWorkspace } from "@/components/review/workspace";
import {
  mockReject,
  mockUpload,
  mockUploadAudio,
  resetMock,
  SAMPLE_TEXT,
} from "@/lib/review/mock";

describe("Audio UI", () => {
  beforeEach(() => {
    resetMock();
  });

  it("(1) UploadStep with an audio file shows the privacy warning and keeps Analyze disabled until I understand is checked, and disables it again when a different file is chosen", () => {
    const audioFile1 = new File(["audio1"], "sample1.mp3", { type: "audio/mpeg" });
    const audioFile2 = new File(["audio2"], "sample2.wav", { type: "audio/wav" });
    const onFile = vi.fn();
    const onAnalyze = vi.fn();

    const { rerender } = render(
      <UploadStep
        file={audioFile1}
        onFile={onFile}
        onAnalyze={onAnalyze}
        loading={false}
        status=""
        error={null}
        onRetry={() => {}}
        audioEnabled={true}
      />,
    );

    expect(
      screen.getByText(/sent to a third-party service \(ElevenLabs\)/i),
    ).toBeInTheDocument();

    const analyzeBtn = screen.getByRole("button", { name: /analyze document/i });
    expect(analyzeBtn).toBeDisabled();

    const checkbox = screen.getByRole("checkbox", { name: /i understand/i });
    expect(checkbox).not.toBeChecked();

    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();
    expect(analyzeBtn).toBeEnabled();

    // Rerender with a different file
    rerender(
      <UploadStep
        file={audioFile2}
        onFile={onFile}
        onAnalyze={onAnalyze}
        loading={false}
        status=""
        error={null}
        onRetry={() => {}}
        audioEnabled={true}
      />,
    );

    const analyzeBtnAfterChange = screen.getByRole("button", {
      name: /analyze document/i,
    });
    expect(analyzeBtnAfterChange).toBeDisabled();
    expect(screen.getByRole("checkbox", { name: /i understand/i })).not.toBeChecked();
  });

  it('(2) with audioEnabled=false an audio file shows "Audio censoring is not available on this server." and Analyze stays disabled even if the box is checked', () => {
    const audioFile = new File(["audio"], "sample.mp3", { type: "audio/mpeg" });

    render(
      <UploadStep
        file={audioFile}
        onFile={() => {}}
        onAnalyze={() => {}}
        loading={false}
        status=""
        error={null}
        onRetry={() => {}}
        audioEnabled={false}
      />,
    );

    expect(
      screen.getByText("Audio censoring is not available on this server."),
    ).toBeInTheDocument();

    const analyzeBtn = screen.getByRole("button", { name: /analyze document/i });
    expect(analyzeBtn).toBeDisabled();

    const checkbox = screen.getByRole("checkbox", { name: /i understand/i });
    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();
    expect(analyzeBtn).toBeDisabled();
  });

  it("(3) a text file shows no privacy warning and Analyze is enabled", () => {
    const textFile = new File(["sample content"], "document.txt", { type: "text/plain" });

    render(
      <UploadStep
        file={textFile}
        onFile={() => {}}
        onAnalyze={() => {}}
        loading={false}
        status=""
        error={null}
        onRetry={() => {}}
        audioEnabled={true}
      />,
    );

    expect(
      screen.queryByText(/sent to a third-party service \(ElevenLabs\)/i),
    ).not.toBeInTheDocument();

    const analyzeBtn = screen.getByRole("button", { name: /analyze document/i });
    expect(analyzeBtn).toBeEnabled();
  });

  it('(4) ReviewWorkspace with the audio snapshot renders an <audio> element whose src starts with "data:audio/wav", the stat "Replaced stretches" with the value 3, the heading "Masked transcript" and a "Download audio" button', async () => {
    const snapshot = await mockUploadAudio();

    const { container } = render(
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

    const audioElement = container.querySelector("audio");
    expect(audioElement).toBeInTheDocument();
    expect(audioElement?.getAttribute("src")?.startsWith("data:audio/wav")).toBe(true);

    expect(screen.getByText("Replaced stretches")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();

    expect(
      screen.getByRole("heading", { name: "Masked transcript" }),
    ).toBeInTheDocument();

    expect(
      screen.getByRole("button", { name: /download audio/i }),
    ).toBeInTheDocument();
  });

  it('(5) with a text snapshot there is no <audio> element and the stat is "Masked words"', async () => {
    const snapshot = await mockUpload(SAMPLE_TEXT);

    const { container } = render(
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

    expect(container.querySelector("audio")).not.toBeInTheDocument();
    expect(screen.getByText("Masked words")).toBeInTheDocument();
    expect(screen.queryByText("Replaced stretches")).not.toBeInTheDocument();
  });

  it('(6) the history sheet of an audio review (after one rejection) labels the old version "Transcript"', async () => {
    await mockUploadAudio();
    const rejectedSnapshot = await mockReject(1, "hide more data");

    render(
      <ReviewWorkspace
        snapshot={rejectedSnapshot}
        busy={false}
        busyMessage=""
        error={null}
        onRetry={null}
        onReject={async () => true}
        onApprove={() => {}}
        onNewDocument={() => {}}
      />,
    );

    const historyBtn = screen.getByRole("button", { name: /history/i });
    fireEvent.click(historyBtn);

    expect(screen.getByText("Transcript")).toBeInTheDocument();
  });
});
