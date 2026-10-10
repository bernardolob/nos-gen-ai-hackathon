import { beforeEach, describe, expect, it } from "vitest";

import { contentTypeFor, parseError } from "@/lib/review/api";
import { mockReject, mockUpload, resetMock } from "@/lib/review/mock";

describe("review contract", () => {
  beforeEach(() => resetMock());

  it("reject returns attempt+1 and stores the rejected version in history", async () => {
    const first = await mockUpload("Utente Maria Santos, NIF 245789123.");
    const next = await mockReject(first.attempt, "ocultar mais");
    expect(next.attempt).toBe(2);
    expect(next.history).toEqual([{ attempt: 1, text: first.text, reason: "ocultar mais" }]);
  });

  it("reject with a stale attempt fails with 409", async () => {
    await mockUpload("Utente Maria Santos.");
    await expect(mockReject(5, "x")).rejects.toMatchObject({ status: 409 });
  });

  it("uploads PDFs as application/pdf and text files as text/plain", () => {
    expect(contentTypeFor(new File(["x"], "a.pdf"))).toBe("application/pdf");
    expect(contentTypeFor(new File(["x"], "a.txt"))).toBe("text/plain");
    expect(contentTypeFor(new File(["x"], "a.docx"))).toBeNull();
  });

  it("falls back to an English message for known error statuses", async () => {
    const res = new Response(JSON.stringify({ detail: 42 }), { status: 502 });
    const err = await parseError(res);
    expect(err.status).toBe(502);
    expect(err.message).toBe("The model did not respond. The current version is unchanged; try again.");
  });

  it("passes through the backend's detail message", async () => {
    const res = new Response(JSON.stringify({ detail: "The version under review has already changed." }), { status: 409 });
    const err = await parseError(res);
    expect(err.status).toBe(409);
    expect(err.message).toBe("The version under review has already changed.");
  });
});
