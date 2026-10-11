import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { UploadStep } from "@/components/anonymizer/steps";
import { instructionHeaders } from "@/lib/review/api";
import { MAX_INSTRUCTIONS } from "@/lib/review/types";

describe("instructionHeaders", () => {
  it("sends nothing for missing or blank instructions", () => {
    expect(instructionHeaders()).toEqual({});
    expect(instructionHeaders("")).toEqual({});
    expect(instructionHeaders("  \n ")).toEqual({});
  });

  it("percent-encodes the text, so accents and line breaks fit in a header", () => {
    const text = "Mascara também a ação.\nNão mascares a clínica.";
    const headers = instructionHeaders(`  ${text}  `);
    expect(Object.keys(headers)).toEqual(["X-User-Instructions"]);
    expect(decodeURIComponent(headers["X-User-Instructions"] as string)).toBe(text);
    expect(headers["X-User-Instructions"]).not.toMatch(/[^\x20-\x7e]/);
  });

  it("accepts the longest allowed text and refuses one character more", () => {
    expect(instructionHeaders("a".repeat(MAX_INSTRUCTIONS))).toHaveProperty("X-User-Instructions");
    expect(() => instructionHeaders("a".repeat(MAX_INSTRUCTIONS + 1))).toThrow(/longer than/);
  });
});

describe("UploadStep instructions field", () => {
  const props = {
    file: null,
    onFile: () => {},
    onAnalyze: () => {},
    loading: false,
    status: "",
    error: null,
    onRetry: () => {},
  };

  it("has an optional instructions field that reports what is typed", () => {
    const onInstructions = vi.fn();
    render(<UploadStep {...props} instructions="" onInstructions={onInstructions} />);

    const field = screen.getByLabelText(/instructions/i);
    expect(field).not.toBeRequired();
    expect(field).toHaveAttribute("maxlength", String(MAX_INSTRUCTIONS));

    fireEvent.change(field, { target: { value: "Do not mask medical information." } });
    expect(onInstructions).toHaveBeenCalledWith("Do not mask medical information.");
  });

  it("shows the character counter and that demo mode ignores the text", () => {
    render(<UploadStep {...props} instructions="abc" onInstructions={() => {}} />);

    expect(screen.getByText(`3/${MAX_INSTRUCTIONS}`)).toBeInTheDocument();
    expect(screen.getByText(/demo mode: instructions are not applied/i)).toBeInTheDocument();
  });

  it("does not block Analyze when the field is empty", () => {
    const file = new File(["texto"], "nota.txt", { type: "text/plain" });
    render(<UploadStep {...props} file={file} instructions="" onInstructions={() => {}} />);

    expect(screen.getByRole("button", { name: /analyze document/i })).toBeEnabled();
  });
});
