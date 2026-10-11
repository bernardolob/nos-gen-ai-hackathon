import type { MediaRegion, RegionBox, RegionPoint } from "./types";

export interface ActiveRenderRegion {
  box: RegionBox;
  polygon: RegionPoint[] | null;
}

export function interpolateBox(b1: RegionBox, b2: RegionBox, t: number): RegionBox {
  const ratio = Math.max(0, Math.min(1, t));
  return {
    x: b1.x + ratio * (b2.x - b1.x),
    y: b1.y + ratio * (b2.y - b1.y),
    width: b1.width + ratio * (b2.width - b1.width),
    height: b1.height + ratio * (b2.height - b1.height),
  };
}

/** Match the backend's box/polygon interpolation, including its box fallback. */
export function getActiveRenderRegion(
  region: MediaRegion,
  timeMs: number,
  isImage: boolean,
): ActiveRenderRegion | null {
  const keys = [...region.keyframes].sort((a, b) => a.time_ms - b.time_ms);
  const first = keys[0];
  if (!first) return null;
  if (isImage) return { box: first.box, polygon: first.polygon ?? null };
  if (timeMs < region.start_ms || timeMs > region.end_ms) return null;
  const index = keys.findIndex((key) => key.time_ms >= timeMs);
  const right = keys[index];
  if (index === -1) {
    const last = keys[keys.length - 1]!;
    return { box: last.box, polygon: last.polygon ?? null };
  }
  if (index === 0 || right!.time_ms === timeMs) {
    return { box: right!.box, polygon: right!.polygon ?? null };
  }
  const left = keys[index - 1]!;
  const ratio = (timeMs - left.time_ms) / (right!.time_ms - left.time_ms);
  const box = interpolateBox(left.box, right!.box, ratio);
  if (!left.polygon || !right!.polygon || left.polygon.length !== right!.polygon.length) {
    return { box, polygon: null };
  }
  const nextPolygon = right!.polygon;
  return {
    box,
    polygon: left.polygon.map((point, i) => ({
      x: point.x + ratio * (nextPolygon[i]!.x - point.x),
      y: point.y + ratio * (nextPolygon[i]!.y - point.y),
    })),
  };
}

/** One reusable renderer per viewer; no canvases are allocated per frame. */
export function createPixelatedPreview() {
  const coarse = document.createElement("canvas");
  const working = document.createElement("canvas");
  return (
    canvas: HTMLCanvasElement,
    source: HTMLImageElement | HTMLVideoElement,
    regions: MediaRegion[],
    timeMs: number,
    width: number,
    height: number,
    isImage: boolean,
  ) => {
    const context = canvas.getContext("2d");
    const workContext = working.getContext("2d");
    const coarseContext = coarse.getContext("2d");
    if (!context || !workContext || !coarseContext) {
      throw new Error("Canvas rendering is unavailable.");
    }
    if (canvas.width !== width) canvas.width = width;
    if (canvas.height !== height) canvas.height = height;
    if (working.width !== width) working.width = width;
    if (working.height !== height) working.height = height;
    context.clearRect(0, 0, width, height);
    workContext.clearRect(0, 0, width, height);
    workContext.drawImage(source, 0, 0, width, height);

    for (const region of regions) {
      const active = getActiveRenderRegion(region, timeMs, isImage);
      if (!active) continue;
      const { box, polygon } = active;
      const left = Math.max(0, Math.round(box.x * width));
      const top = Math.max(0, Math.round(box.y * height));
      const right = Math.min(width, Math.round((box.x + box.width) * width));
      const bottom = Math.min(height, Math.round((box.y + box.height) * height));
      const areaWidth = right - left;
      const areaHeight = bottom - top;
      if (areaWidth < 1 || areaHeight < 1) continue;
      const cellSize = Math.max(24, Math.ceil(Math.min(areaWidth, areaHeight) / 5));
      const columns = Math.max(1, Math.ceil(areaWidth / cellSize));
      const rows = Math.max(1, Math.ceil(areaHeight / cellSize));
      if (coarse.width !== columns) coarse.width = columns;
      if (coarse.height !== rows) coarse.height = rows;
      coarseContext.clearRect(0, 0, columns, rows);
      coarseContext.imageSmoothingEnabled = true;
      coarseContext.imageSmoothingQuality = "high";
      coarseContext.drawImage(working, left, top, areaWidth, areaHeight, 0, 0, columns, rows);

      // Composite in manifest order, like the export, including overlapping masks.
      for (const target of [context, workContext]) {
        target.save();
        try {
          if (polygon) {
            target.beginPath();
            polygon.forEach((point, index) => {
              if (index === 0) target.moveTo(point.x * width, point.y * height);
              else target.lineTo(point.x * width, point.y * height);
            });
            target.closePath();
            target.clip();
          }
          target.imageSmoothingEnabled = false;
          target.drawImage(coarse, left, top, areaWidth, areaHeight);
          target.fillStyle = "rgba(43, 69, 90, 0.22)";
          target.fillRect(left, top, areaWidth, areaHeight);
        } finally {
          target.restore();
        }
      }
    }
  };
}
