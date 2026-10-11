import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ReviewWorkspace } from "@/components/review/workspace";
import { mockCurrent, mockUploadDocument, resetMock } from "@/lib/review/mock";
import type { Snapshot } from "@/lib/review/types";

function workspace(snapshot: Snapshot, onApprove = vi.fn()) {
  return (
    <ReviewWorkspace
      snapshot={snapshot}
      busy={false}
      busyMessage=""
      error={null}
      onRetry={null}
      onReject={async () => true}
      onApprove={onApprove}
      onNewDocument={() => {}}
    />
  );
}

describe("Document image review", () => {
  beforeEach(() => {
    resetMock();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
  });

  it("shows tabs and shared placements, saves edited masks before approval", async () => {
    const snapshot = await mockUploadDocument("docx", "report.docx");
    const onApprove = vi.fn();
    render(workspace(snapshot, onApprove));
    expect(screen.getByRole("button", { name: "Download .docx" })).toBeDisabled();
    fireEvent.click(screen.getByRole("tab", { name: "Images (1)" }));
    expect(screen.getByText(/Masks apply to all 1 placements/)).toBeInTheDocument();
    const mask = document.querySelector(".redaction-region")!;
    fireEvent.pointerDown(mask, { clientX: 200, clientY: 100, pointerId: 1 });
    fireEvent.click(screen.getByRole("button", { name: "Remove mask" }));
    expect(document.querySelectorAll(".redaction-region")).toHaveLength(0);
    fireEvent.click(screen.getByRole("tab", { name: "Text" }));
    fireEvent.click(screen.getByRole("tab", { name: "Images (1)" }));
    expect(document.querySelectorAll(".redaction-region")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Approve version" }));
    await waitFor(() => expect(onApprove).toHaveBeenCalledOnce());
    expect((await mockCurrent()).document?.images[0]?.regions).toHaveLength(0);
  });

  it("blocks approval during analysis and failure", async () => {
    const snapshot = await mockUploadDocument("pdf", "scan.pdf");
    const { rerender } = render(workspace({ ...snapshot, status: "processing" }));
    expect(screen.getByRole("button", { name: "Approve version" })).toBeDisabled();
    rerender(workspace({ ...snapshot, status: "failed", error: "Image analysis failed" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Image analysis failed");
    expect(screen.getByRole("button", { name: "Approve version" })).toBeDisabled();
  });

  it("does not approve when edited masks cannot be saved", async () => {
    const snapshot = await mockUploadDocument("pdf", "scan.pdf");
    const onApprove = vi.fn();
    render(workspace(snapshot, onApprove));
    fireEvent.click(screen.getByRole("tab", { name: "Images (1)" }));
    fireEvent.pointerDown(document.querySelector(".redaction-region")!, {
      clientX: 200,
      clientY: 100,
      pointerId: 1,
    });
    fireEvent.click(screen.getByRole("button", { name: "Remove mask" }));
    resetMock();
    fireEvent.click(screen.getByRole("button", { name: "Approve version" }));
    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("version under review has changed"),
    );
    expect(onApprove).not.toHaveBeenCalled();
  });
});
