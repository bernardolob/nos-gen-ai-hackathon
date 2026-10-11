import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MaskedText } from "@/components/review/workspace";

describe("MaskedText Hover Tooltip", () => {
  it("renders asterisks and reveals the original word on hover", async () => {
    const originalText = "Patient: Maria Santos, born on 12/03/1968.";
    const maskedText = "Patient: * *, born on *.";

    render(<MaskedText text={maskedText} originalText={originalText} />);

    // Check aria-labels identifying the redacted tokens
    const mariaMark = screen.getByLabelText("redacted: Maria");
    expect(mariaMark).toBeInTheDocument();
    expect(mariaMark).toHaveTextContent("*");

    const santosMark = screen.getByLabelText("redacted: Santos");
    expect(santosMark).toBeInTheDocument();

    const dateMark = screen.getByLabelText("redacted: 12/03/1968");
    expect(dateMark).toBeInTheDocument();

    // Focus / hover over the first asterisk
    fireEvent.focus(mariaMark);

    // The tooltip reveals the original word
    expect(await screen.findByText("Maria")).toBeInTheDocument();
  });

  it("falls back gracefully when originalText is not provided", () => {
    render(<MaskedText text="Hello * world" />);

    const mark = screen.getByLabelText("redacted data");
    expect(mark).toBeInTheDocument();
    expect(mark).toHaveTextContent("*");
  });
});
