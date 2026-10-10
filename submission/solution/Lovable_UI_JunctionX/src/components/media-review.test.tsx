// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MediaReview, type MediaRegion } from "./media-review";

const REGION: MediaRegion = {
  id: "region-1",
  category: "identificacao",
  kind: "identity_document",
  reason: "Documento de identificação visível.",
  confidence: "certo",
  source: "gemini",
  start_ms: 0,
  end_ms: 0,
  keyframes: [{
    time_ms: 0,
    box: { x: 0.1, y: 0.1, width: 0.3, height: 0.2 },
  }],
};

const FACE_REGION: MediaRegion = {
  ...REGION,
  id: "face-1",
  kind: "face",
  source: "face_detector",
  keyframes: [{
    time_ms: 0,
    box: { x: 0.2, y: 0.15, width: 0.4, height: 0.5 },
    polygon: Array.from({ length: 32 }, (_, index) => ({
      x: 0.4 + Math.sin(index * 2 * Math.PI / 32) * 0.2,
      y: 0.4 - Math.cos(index * 2 * Math.PI / 32) * 0.25,
    })),
  }],
};

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("MediaReview", () => {
  it("requires confirmation before removing and saves the edited manifest", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const save = vi.fn().mockResolvedValue(undefined);
    const { container } = render(<MediaReview
      api="http://127.0.0.1:8000"
      attempt={1}
      kind="image"
      media={{
        source_url: "/api/media/source",
        filename: "foto.jpg",
        width: 100,
        height: 80,
      }}
      regions={[REGION]}
      onSave={save}
    />);

    const box = container.querySelector(".redaction-region");
    expect(box).not.toBeNull();
    fireEvent.pointerDown(box!);
    fireEvent.click(await screen.findByRole("button", { name: "Remover" }));
    expect(window.confirm).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Guardar regiões/ }));
    await waitFor(() => expect(save).toHaveBeenCalledWith([]));
  });

  it("previews pixelated regions and exposes no detected value", () => {
    const { container } = render(<MediaReview
      api="http://127.0.0.1:8000"
      attempt={2}
      kind="image"
      media={{
        source_url: "/api/media/source",
        filename: "foto.jpg",
        width: 100,
        height: 80,
      }}
      regions={[REGION]}
      onSave={async () => undefined}
    />);
    expect(container.querySelector(".redaction-region.pending")).toBeTruthy();
    expect(screen.getByText(/regiões ficam pixelizadas/)).toBeTruthy();
    expect(within(container).getByText("1 regiões")).toBeTruthy();
    expect(screen.queryByText(/123456789/)).toBeNull();
  });

  it("paints a detail-free canvas over the face when the image loads", async () => {
    const drawImage = vi.fn();
    const context = {
      clearRect: vi.fn(), drawImage,
      fillRect: vi.fn(),
      imageSmoothingEnabled: true,
      fillStyle: "",
    };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockReturnValue(context as unknown as CanvasRenderingContext2D);
    const { container } = render(<MediaReview
      api="http://127.0.0.1:8000"
      attempt={3}
      kind="image"
      media={{
        source_url: "/api/media/source",
        filename: "foto.jpg",
        width: 100,
        height: 80,
      }}
      regions={[REGION]}
      onSave={async () => undefined}
    />);
    const image = screen.getByAltText("Imagem em revisão");
    Object.defineProperty(image, "naturalWidth", { value: 100 });
    Object.defineProperty(image, "naturalHeight", { value: 80 });
    fireEvent.load(image);
    await waitFor(() => expect(container.querySelector(
      ".redaction-region.pending")).toBeNull());
    expect(container.querySelector(".redaction-preview")).toBeTruthy();
    expect(drawImage).toHaveBeenCalledTimes(2);
    expect(drawImage.mock.calls[0]?.[0]).toBe(image);
    expect(drawImage.mock.calls[0]?.slice(1)).toEqual(
      [10, 8, 30, 16, 0, 0, 2, 1]);
    expect(context.imageSmoothingEnabled).toBe(false);
    expect(context.fillStyle).toBe("rgba(43, 69, 90, 0.22)");
    expect(context.fillRect).toHaveBeenCalledWith(10, 8, 30, 16);
  });

  it("clips the preview and review outline to a face polygon", async () => {
    const context = {
      clearRect: vi.fn(), drawImage: vi.fn(), fillRect: vi.fn(),
      save: vi.fn(), restore: vi.fn(), beginPath: vi.fn(),
      moveTo: vi.fn(), lineTo: vi.fn(), closePath: vi.fn(), clip: vi.fn(),
      imageSmoothingEnabled: true,
      fillStyle: "",
    };
    vi.spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockReturnValue(context as unknown as CanvasRenderingContext2D);
    const { container } = render(<MediaReview
      api="http://127.0.0.1:8000"
      attempt={6}
      kind="image"
      media={{
        source_url: "/api/media/source",
        filename: "face.jpg",
        width: 100,
        height: 100,
      }}
      regions={[FACE_REGION]}
      onSave={async () => undefined}
    />);
    const image = screen.getByAltText("Imagem em revisão");
    Object.defineProperty(image, "naturalWidth", { value: 100 });
    Object.defineProperty(image, "naturalHeight", { value: 100 });
    fireEvent.load(image);
    await waitFor(() => expect(context.clip).toHaveBeenCalled());
    expect(context.save).toHaveBeenCalledTimes(1);
    expect(context.restore).toHaveBeenCalledTimes(1);
    expect(context.moveTo).toHaveBeenCalledWith(40, expect.closeTo(15, 8));
    expect(context.lineTo).toHaveBeenCalledTimes(31);
    expect(container.querySelector(".redaction-region.polygon polygon"))
      .not.toBeNull();
  });

  it("keeps a full-clip video region visible at the playback end", () => {
    const face: MediaRegion = {
      ...REGION,
      kind: "face",
      end_ms: 1300,
      keyframes: [
        { time_ms: 0, box: REGION.keyframes[0]!.box },
        { time_ms: 1167, box: { x: 0.45, y: 0.5, width: 0.2, height: 0.2 } },
      ],
    };
    const { container } = render(<MediaReview
      api="http://127.0.0.1:8000"
      attempt={4}
      kind="video"
      media={{
        source_url: "/api/media/source",
        filename: "clip.mp4",
        width: 576,
        height: 1024,
        duration_ms: 1300,
      }}
      regions={[face]}
      onSave={async () => undefined}
    />);
    fireEvent.change(screen.getByRole("slider", { name: "Instante do vídeo" }), {
      target: { value: "1300" },
    });
    const box = container.querySelector(".redaction-region") as HTMLElement;
    expect(box).not.toBeNull();
    expect(box.style.left).toBe("45%");
    expect(box.style.top).toBe("50%");
  });

  it("can replace a selected static box with an automatically tracked region", async () => {
    const tracked: MediaRegion = {
      ...REGION,
      source: "user",
      end_ms: 1300,
      keyframes: [
        { time_ms: 0, box: REGION.keyframes[0]!.box },
        { time_ms: 1000, box: { x: 0.4, y: 0.2, width: 0.3, height: 0.2 } },
      ],
    };
    const onTrack = vi.fn().mockResolvedValue(tracked);
    const { container } = render(<MediaReview
      api="http://127.0.0.1:8000"
      attempt={5}
      kind="video"
      media={{
        source_url: "/api/media/source",
        filename: "clip.mp4",
        width: 576,
        height: 1024,
        duration_ms: 1300,
      }}
      regions={[{ ...REGION, source: "user", end_ms: 1300 }]}
      onSave={async () => undefined}
      onTrack={onTrack}
    />);
    fireEvent.pointerDown(container.querySelector(".redaction-region")!);
    fireEvent.click(await screen.findByRole("button", { name: "Rastrear caixa" }));
    await waitFor(() => expect(onTrack).toHaveBeenCalledWith(
      expect.objectContaining({ id: "region-1" }), 0));
    expect(await screen.findByText(/2 fotogramas-chave/)).toBeTruthy();
  });
});
