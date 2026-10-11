import { useEffect, useRef } from "react";

import type { MediaRegion, RegionBox } from "@/lib/review/types";

/** One region as it is drawn at this instant (see getActiveRenderRegion). */
export interface LiveRegion {
  region: MediaRegion;
  box: RegionBox;
}

const FACE_CELLS = 6;
const FACE_MARGIN = 1.08;
const MOSAIC_CELL = 24;
const MAX_SIDE = 960;

/**
 * The blur drawn live over a playing video, from the frames the browser is
 * showing: a face is reduced to a few colour cells, enlarged smoothly and
 * shown through an ellipse; anything else is a coarse mosaic. It is only an
 * approximation of the export (that one is drawn by the backend, and is what
 * the paused picture shows); it exists so the preview does not vanish while
 * the video plays.
 */
export function LiveBlur({
  video,
  regions,
}: {
  video: HTMLVideoElement | null;
  regions: LiveRegion[];
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx || !video || !video.videoWidth) return;
    const scale = Math.min(1, MAX_SIDE / Math.max(video.videoWidth, video.videoHeight));
    const width = Math.round(video.videoWidth * scale);
    const height = Math.round(video.videoHeight * scale);
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    ctx.clearRect(0, 0, width, height);
    const small = document.createElement("canvas");
    const sctx = small.getContext("2d");
    if (!sctx) return;
    for (const { region, box } of regions) {
      const x = box.x * width;
      const y = box.y * height;
      const w = box.width * width;
      const h = box.height * height;
      if (w < 2 || h < 2) continue;
      const isFace = region.kind === "face" && Math.min(w, h) >= 8;
      const cell = isFace ? Math.max(4, Math.min(w, h) / FACE_CELLS) : MOSAIC_CELL;
      small.width = Math.max(1, Math.ceil(w / cell));
      small.height = Math.max(1, Math.ceil(h / cell));
      sctx.drawImage(video, box.x * video.videoWidth, box.y * video.videoHeight, box.width * video.videoWidth, box.height * video.videoHeight, 0, 0, small.width, small.height);
      ctx.save();
      if (isFace) {
        ctx.beginPath();
        ctx.ellipse(x + w / 2, y + h / 2, (w / 2) * FACE_MARGIN, (h / 2) * FACE_MARGIN, 0, 0, Math.PI * 2);
        ctx.clip();
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = "high";
        ctx.filter = `blur(${Math.round(cell * 0.5)}px)`;
        const grow = (FACE_MARGIN - 1) * 0.5;
        ctx.drawImage(small, x - w * grow, y - h * grow, w * (1 + 2 * grow), h * (1 + 2 * grow));
      } else {
        ctx.imageSmoothingEnabled = false;
        ctx.drawImage(small, x, y, w, h);
        ctx.fillStyle = "rgba(43, 69, 90, 0.22)";
        ctx.fillRect(x, y, w, h);
      }
      ctx.restore();
    }
  });

  return (
    <canvas
      ref={canvasRef}
      data-testid="live-blur"
      aria-hidden
      // The bottom strip is left to the player's controls.
      style={{ clipPath: "inset(0 0 44px 0)" }}
      className="pointer-events-none absolute inset-0 h-full w-full select-none object-contain"
    />
  );
}
