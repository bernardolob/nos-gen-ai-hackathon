import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UploadStep } from "@/components/anonymizer/steps";

describe("UploadStep media", () => {
  it("with an image file selected, the privacy alert shows and Analyze document stays disabled until I understand is ticked", () => {
    const imageFile = new File(["dummy image"], "photo.png", { type: "image/png" });
    const onFile = vi.fn();
    const onAnalyze = vi.fn();

    render(
      <UploadStep
        file={imageFile}
        onFile={onFile}
        onAnalyze={onAnalyze}
        loading={false}
        status=""
        error={null}
        onRetry={() => {}}
      />,
    );

    expect(
      screen.getByText(/Sampled frames are sent to a third-party AI model \(Gemini\)/i),
    ).toBeInTheDocument();

    const analyzeBtn = screen.getByRole("button", { name: /analyze document/i });
    expect(analyzeBtn).toBeDisabled();

    const checkbox = screen.getByRole("checkbox", { name: /i understand/i });
    expect(checkbox).not.toBeChecked();

    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();
    expect(analyzeBtn).toBeEnabled();
  });

  it("with loading=true and progress={stage:'extrair fotogramas',completed:1,total:4} it shows Extracting frames and 25%", () => {
    render(
      <UploadStep
        file={null}
        onFile={() => {}}
        onAnalyze={() => {}}
        loading={true}
        status="Processing"
        progress={{
          stage: "extrair fotogramas",
          completed: 1,
          total: 4,
        }}
        error={null}
        onRetry={() => {}}
      />,
    );

    expect(screen.getByText("Extracting frames")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
  });
});
