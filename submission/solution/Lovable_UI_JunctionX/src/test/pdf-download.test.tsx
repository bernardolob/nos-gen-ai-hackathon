import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ReviewWorkspace } from "@/components/review/workspace";
import { anonymizedPdfUrl } from "@/lib/review/api";
import { mockUpload, resetMock, SAMPLE_TEXT } from "@/lib/review/mock";
import type { Snapshot } from "@/lib/review/types";

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

describe("Anonymized PDF", () => {
  beforeEach(() => resetMock());
  afterEach(() => vi.restoreAllMocks());

  it("a document that came from a PDF has a PDF url; one from text has none", async () => {
    const fromPdf = await mockUpload(SAMPLE_TEXT, true, true);
    expect(anonymizedPdfUrl(fromPdf)).toMatch(/^data:application\/pdf/);
    const fromText = await mockUpload(SAMPLE_TEXT);
    expect(fromText.pdf_url).toBeNull();
    expect(anonymizedPdfUrl(fromText)).toBeNull();
  });

  it("shows Download PDF only when there is a PDF", async () => {
    const { unmount } = show(await mockUpload(SAMPLE_TEXT, true, true));
    expect(screen.getByRole("button", { name: /download pdf/i })).toBeInTheDocument();
    unmount();
    show(await mockUpload(SAMPLE_TEXT));
    expect(screen.queryByRole("button", { name: /download pdf/i })).not.toBeInTheDocument();
  });

  it("downloads the PDF of the version under review", async () => {
    const snapshot = await mockUpload(SAMPLE_TEXT, true, true);
    const fetchMock = vi.fn(async () => new Response(new Blob(["%PDF"]), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    URL.createObjectURL = vi.fn(() => "blob:pdf");
    URL.revokeObjectURL = vi.fn();
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    show(snapshot);
    fireEvent.click(screen.getByRole("button", { name: /download pdf/i }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith(snapshot.pdf_url);
  });

  it("shows the server's message when the PDF cannot be generated", async () => {
    const snapshot = await mockUpload(SAMPLE_TEXT, true, true);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "Não foi possível gerar o PDF anonimizado." }), { status: 502 })),
    );
    show(snapshot);
    fireEvent.click(screen.getByRole("button", { name: /download pdf/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível gerar o PDF anonimizado.");
  });
});
