import { useEffect, useMemo, useRef, useState } from "react";
import { Crosshair, Loader2, Plus, Shield, Sparkles, Trash2, User } from "lucide-react";

import { Button } from "@/components/ui/button";
import type {
  Confidence,
  MediaRegion,
  RegionBox,
  RegionKeyframe,
  RegionKind,
  RegionPoint,
  RegionSource,
  Snapshot,
} from "@/lib/review/types";
import { mediaSourceUrl } from "@/lib/review/api";

export const CATEGORY_LABELS: Record<string, string> = {
  identificacao: "Personal identification",
  biometrico: "Biometric",
  biometricos: "Biometric",
  saude: "Health",
  financeiro: "Financial",
  financeiros: "Financial",
  genetico: "Genetic",
  geneticos: "Genetic",
  origem: "Origin, religion, politics or orientation",
  origem_religiao_politica: "Origin, religion, politics or orientation",
  familia: "Family life",
  comportamento: "Personal behaviour",
  comportamentos: "Personal behaviour",
  quasi: "Quasi-identifiers",
  quasi_identificador: "Quasi-identifiers",
};

export const categoryLabel = (cat: string): string => CATEGORY_LABELS[cat] ?? cat;

export function getCategoryVar(category: string): string {
  switch (category) {
    case "identificacao":
      return "var(--cat-identificacao)";
    case "saude":
      return "var(--cat-saude)";
    case "genetico":
    case "geneticos":
      return "var(--cat-geneticos)";
    case "biometrico":
    case "biometricos":
      return "var(--cat-biometricos)";
    case "origem":
    case "origem_religiao_politica":
      return "var(--cat-origem)";
    case "financeiro":
    case "financeiros":
      return "var(--cat-financeiros)";
    case "familia":
      return "var(--cat-familia)";
    case "comportamento":
    case "comportamentos":
      return "var(--cat-comportamentos)";
    case "quasi":
    case "quasi_identificador":
      return "var(--cat-quasi)";
    default:
      return "var(--cat-identificacao)";
  }
}

export const KIND_LABELS: Record<RegionKind | string, string> = {
  face: "Face",
  identity_document: "ID document",
  plate: "Plate",
  signature: "Signature",
  text: "Text",
  biometric: "Biometric",
  code: "Code",
  other: "Other",
};

export const formatKind = (kind: string): string => KIND_LABELS[kind] ?? kind;

export const CONFIDENCE_LABELS: Record<Confidence | string, string> = {
  certo: "Certain",
  provavel: "Probable",
  incerto: "Uncertain",
};

export const formatConfidence = (conf: string): string => CONFIDENCE_LABELS[conf] ?? conf;

export const SOURCE_LABELS: Record<RegionSource | string, string> = {
  gemini: "AI",
  face_detector: "Face detector",
  user: "You",
};

export const formatSource = (src: string): string => SOURCE_LABELS[src] ?? src;

export function interpolateBox(b1: RegionBox, b2: RegionBox, t: number): RegionBox {
  const clampT = Math.max(0, Math.min(1, t));
  return {
    x: Number((b1.x + clampT * (b2.x - b1.x)).toFixed(6)),
    y: Number((b1.y + clampT * (b2.y - b1.y)).toFixed(6)),
    width: Number((b1.width + clampT * (b2.width - b1.width)).toFixed(6)),
    height: Number((b1.height + clampT * (b2.height - b1.height)).toFixed(6)),
  };
}

export interface ActiveRenderRegion {
  box: RegionBox;
  polygon: RegionPoint[] | null;
}

export function getActiveRenderRegion(
  region: MediaRegion,
  currentTimeMs: number,
  isImage: boolean,
): ActiveRenderRegion | null {
  if (!region.keyframes || region.keyframes.length === 0) return null;
  const firstKf = region.keyframes[0];
  if (!firstKf) return null;

  if (isImage) {
    return {
      box: firstKf.box,
      polygon: firstKf.polygon ?? null,
    };
  }

  if (currentTimeMs < region.start_ms || currentTimeMs > region.end_ms) {
    return null;
  }

  const sorted = [...region.keyframes].sort((a, b) => a.time_ms - b.time_ms);
  const first = sorted[0];
  const last = sorted[sorted.length - 1];
  if (!first || !last) return null;

  if (sorted.length === 1 || currentTimeMs <= first.time_ms) {
    return {
      box: first.box,
      polygon: first.polygon ?? null,
    };
  }

  if (currentTimeMs >= last.time_ms) {
    return {
      box: last.box,
      polygon: last.polygon ?? null,
    };
  }

  let prev: RegionKeyframe = first;
  let next: RegionKeyframe = last;
  for (let i = 0; i < sorted.length - 1; i++) {
    const cur = sorted[i];
    const nxt = sorted[i + 1];
    if (cur && nxt && cur.time_ms <= currentTimeMs && nxt.time_ms >= currentTimeMs) {
      prev = cur;
      next = nxt;
      break;
    }
  }

  if (next.time_ms === prev.time_ms) {
    return {
      box: prev.box,
      polygon: prev.polygon ?? null,
    };
  }

  const t = (currentTimeMs - prev.time_ms) / (next.time_ms - prev.time_ms);
  const box = interpolateBox(prev.box, next.box, t);

  let polygon: RegionPoint[] | null = null;
  if (prev.polygon && next.polygon && prev.polygon.length === next.polygon.length) {
    const nextPoly = next.polygon;
    polygon = prev.polygon.map((p, idx) => {
      const np = nextPoly[idx];
      if (!np) return p;
      return {
        x: Number((p.x + t * (np.x - p.x)).toFixed(6)),
        y: Number((p.y + t * (np.y - p.y)).toFixed(6)),
      };
    });
  } else {
    polygon = t < 0.5 ? prev.polygon ?? null : next.polygon ?? null;
  }

  return { box, polygon };
}

export function getActiveKeyframe(
  region: MediaRegion,
  currentTimeMs: number,
  isImage: boolean,
): RegionKeyframe | null {
  const active = getActiveRenderRegion(region, currentTimeMs, isImage);
  if (!active) return null;
  return {
    time_ms: currentTimeMs,
    box: active.box,
    polygon: active.polygon,
  };
}

export function updateRegionBoxAtTime(
  region: MediaRegion,
  newBox: RegionBox,
  currentTimeMs: number,
  isImage: boolean,
): MediaRegion {
  if (isImage) {
    return {
      ...region,
      keyframes: [
        {
          time_ms: 0,
          box: { ...newBox },
          polygon: null,
        },
      ],
    };
  }

  const kfs = [...region.keyframes];
  const existingIdx = kfs.findIndex((k) => k.time_ms === currentTimeMs);
  if (existingIdx >= 0) {
    kfs[existingIdx] = {
      time_ms: currentTimeMs,
      box: { ...newBox },
      polygon: null,
    };
  } else {
    kfs.push({
      time_ms: currentTimeMs,
      box: { ...newBox },
      polygon: null,
    });
    kfs.sort((a, b) => a.time_ms - b.time_ms);
  }

  const start_ms = Math.min(region.start_ms, currentTimeMs);
  const end_ms = Math.max(region.end_ms, currentTimeMs);

  return {
    ...region,
    start_ms,
    end_ms,
    keyframes: kfs,
  };
}

/* ---------------- Media Center Card Viewer ---------------- */

export function MediaViewer({
  snapshot,
  currentTimeMs,
  onTimeUpdate,
  selectedRegionId,
  onSelectRegion,
  videoRef,
  regions,
  onUpdateRegionBox,
  onAddRegion,
  onRemoveRegion,
  isDrawing = false,
  onToggleDrawMode,
  previewUrl = null,
  onPlayingChange,
}: {
  snapshot: Snapshot;
  currentTimeMs: number;
  onTimeUpdate: (ms: number) => void;
  selectedRegionId: string | null;
  onSelectRegion: (id: string | null) => void;
  videoRef?: React.RefObject<HTMLVideoElement | null>;
  regions?: MediaRegion[];
  onUpdateRegionBox?: (regionId: string, newBox: RegionBox) => void;
  onAddRegion?: (newRegion: MediaRegion) => void;
  onRemoveRegion?: (regionId: string) => void;
  isDrawing?: boolean;
  onToggleDrawMode?: () => void;
  /** The file with the redaction applied (see previewMedia); drawn over the original. */
  previewUrl?: string | null;
  onPlayingChange?: (playing: boolean) => void;
}) {
  const isImage = snapshot.kind === "image";
  const sourceUrl = mediaSourceUrl(snapshot);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const activeRegions = regions ?? snapshot.regions;

  const aspectRatio =
    snapshot.media.width && snapshot.media.height
      ? `${snapshot.media.width} / ${snapshot.media.height}`
      : "16 / 9";

  // Smooth frame updates during video playback
  useEffect(() => {
    const vid = videoRef?.current;
    if (!vid || isImage) return;

    let frameId: number | null = null;
    let running = true;

    const hasRvfc = typeof (vid as any).requestVideoFrameCallback === "function";

    const onFrame = () => {
      if (!running) return;
      onTimeUpdate(Math.round(vid.currentTime * 1000));
      if (hasRvfc) {
        frameId = (vid as any).requestVideoFrameCallback(onFrame);
      } else if (!vid.paused && !vid.ended) {
        frameId = requestAnimationFrame(onFrame);
      }
    };

    const startLoop = () => {
      if (frameId !== null) return;
      if (hasRvfc) {
        frameId = (vid as any).requestVideoFrameCallback(onFrame);
      } else {
        frameId = requestAnimationFrame(onFrame);
      }
    };

    const stopLoop = () => {
      if (frameId !== null) {
        if (typeof (vid as any).cancelVideoFrameCallback === "function") {
          (vid as any).cancelVideoFrameCallback(frameId);
        } else {
          cancelAnimationFrame(frameId);
        }
        frameId = null;
      }
      onTimeUpdate(Math.round(vid.currentTime * 1000));
    };

    const onSeeking = () => {
      onTimeUpdate(Math.round(vid.currentTime * 1000));
    };

    vid.addEventListener("play", startLoop);
    vid.addEventListener("pause", stopLoop);
    vid.addEventListener("ended", stopLoop);
    vid.addEventListener("seeking", onSeeking);
    vid.addEventListener("timeupdate", onSeeking);

    if (!vid.paused && !vid.ended) {
      startLoop();
    }

    return () => {
      running = false;
      vid.removeEventListener("play", startLoop);
      vid.removeEventListener("pause", stopLoop);
      vid.removeEventListener("ended", stopLoop);
      vid.removeEventListener("seeking", onSeeking);
      vid.removeEventListener("timeupdate", onSeeking);
      stopLoop();
    };
  }, [videoRef, isImage, onTimeUpdate]);

  // Tell the parent when the video plays: the blur preview is a still, so it
  // is only shown while the video is paused.
  useEffect(() => {
    const vid = videoRef?.current;
    if (!vid || isImage || !onPlayingChange) return;
    const playing = () => onPlayingChange(true);
    const stopped = () => onPlayingChange(false);
    vid.addEventListener("play", playing);
    vid.addEventListener("pause", stopped);
    vid.addEventListener("ended", stopped);
    onPlayingChange(!vid.paused && !vid.ended);
    return () => {
      vid.removeEventListener("play", playing);
      vid.removeEventListener("pause", stopped);
      vid.removeEventListener("ended", stopped);
    };
  }, [videoRef, isImage, onPlayingChange]);

  const renderedRegions = useMemo(() => {
    return activeRegions
      .map((region) => {
        const active = getActiveRenderRegion(region, currentTimeMs, isImage);
        return active ? { region, ...active } : null;
      })
      .filter((item): item is { region: MediaRegion; box: RegionBox; polygon: RegionPoint[] | null } => item !== null);
  }, [activeRegions, currentTimeMs, isImage]);

  // Keyboard navigation & controls for selected box:
  // Arrow keys nudge by 0.5% (Shift = 2%), Delete removes, Escape deselects
  useEffect(() => {
    if (!selectedRegionId) return;

    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.tagName === "SELECT")) {
        return;
      }

      if (e.key === "Escape") {
        e.preventDefault();
        onSelectRegion(null);
        return;
      }

      if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        onRemoveRegion?.(selectedRegionId);
        return;
      }

      if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) {
        e.preventDefault();
        const step = e.shiftKey ? 0.02 : 0.005;
        const currentActive = renderedRegions.find((r) => r.region.id === selectedRegionId);
        if (!currentActive) return;
        const b = currentActive.box;

        let newX = b.x;
        let newY = b.y;

        if (e.key === "ArrowLeft") newX = Math.max(0, Math.min(1 - b.width, b.x - step));
        if (e.key === "ArrowRight") newX = Math.max(0, Math.min(1 - b.width, b.x + step));
        if (e.key === "ArrowUp") newY = Math.max(0, Math.min(1 - b.height, b.y - step));
        if (e.key === "ArrowDown") newY = Math.max(0, Math.min(1 - b.height, b.y + step));

        onUpdateRegionBox?.(selectedRegionId, {
          x: Number(newX.toFixed(6)),
          y: Number(newY.toFixed(6)),
          width: b.width,
          height: b.height,
        });
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedRegionId, renderedRegions, onSelectRegion, onRemoveRegion, onUpdateRegionBox]);

  // Drawing state
  const [drawingPreview, setDrawingPreview] = useState<{ x: number; y: number; width: number; height: number } | null>(null);
  const drawStartRef = useRef<{ x: number; y: number } | null>(null);

    const getNormCoords = (e: PointerEvent | React.PointerEvent) => {
    if (!containerRef.current) return { x: 0, y: 0 };
    const rect = containerRef.current.getBoundingClientRect();
    const width = rect.width || 1;
    const height = rect.height || 1;
    const clientX =
      typeof e.clientX === "number"
        ? e.clientX
        : typeof (e as any).nativeEvent?.clientX === "number"
        ? (e as any).nativeEvent.clientX
        : 0;
    const clientY =
      typeof e.clientY === "number"
        ? e.clientY
        : typeof (e as any).nativeEvent?.clientY === "number"
        ? (e as any).nativeEvent.clientY
        : 0;
    const x = Math.max(0, Math.min(1, (clientX - rect.left) / width));
    const y = Math.max(0, Math.min(1, (clientY - rect.top) / height));
    return { x, y };
  };

  const handlePointerDownContainer = (e: React.PointerEvent) => {
    if (!isDrawing) return;
    e.preventDefault();
    const { x, y } = getNormCoords(e);
    drawStartRef.current = { x, y };
    setDrawingPreview({ x, y, width: 0, height: 0 });

    const onPointerMove = (ev: PointerEvent) => {
            if (!drawStartRef.current) return;
      const cur = getNormCoords(ev);
      const x1 = Math.min(drawStartRef.current.x, cur.x);
      const y1 = Math.min(drawStartRef.current.y, cur.y);
      const w = Math.abs(cur.x - drawStartRef.current.x);
      const h = Math.abs(cur.y - drawStartRef.current.y);
      setDrawingPreview({ x: x1, y: y1, width: w, height: h });
    };

    const onPointerUp = (ev: PointerEvent) => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      document.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerup", onPointerUp);
      if (!drawStartRef.current) return;

      const cur = getNormCoords(ev);
      const x1 = Math.min(drawStartRef.current.x, cur.x);
      const y1 = Math.min(drawStartRef.current.y, cur.y);
      const w = Math.max(0.02, Math.abs(cur.x - drawStartRef.current.x));
      const h = Math.max(0.02, Math.abs(cur.y - drawStartRef.current.y));
      const clampedX = Math.max(0, Math.min(1 - w, x1));
      const clampedY = Math.max(0, Math.min(1 - h, y1));

      const newId =
        typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
          ? crypto.randomUUID()
          : `region-${Date.now()}`;

      const newRegion: MediaRegion = {
        id: newId,
        kind: "other",
        category: "identificacao",
        confidence: "certo",
        source: "user",
        reason: "Added by the reviewer",
        start_ms: isImage ? 0 : currentTimeMs,
        end_ms: isImage ? 0 : currentTimeMs,
        keyframes: [
          {
            time_ms: isImage ? 0 : currentTimeMs,
            box: {
              x: Number(clampedX.toFixed(6)),
              y: Number(clampedY.toFixed(6)),
              width: Number(w.toFixed(6)),
              height: Number(h.toFixed(6)),
            },
            polygon: null,
          },
        ],
      };

      drawStartRef.current = null;
      setDrawingPreview(null);
      onAddRegion?.(newRegion);
      onSelectRegion(newId);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  };

  // Dragging and resizing box
  const startDragBox = (e: React.PointerEvent, regionId: string, currentBox: RegionBox) => {
        e.stopPropagation();
    e.preventDefault();
    onSelectRegion(regionId);
    const startCoords = getNormCoords(e);
    const origBox = { ...currentBox };

    const onPointerMove = (ev: PointerEvent) => {
            const cur = getNormCoords(ev);
      const dx = cur.x - startCoords.x;
      const dy = cur.y - startCoords.y;

      const newX = Math.max(0, Math.min(1 - origBox.width, origBox.x + dx));
      const newY = Math.max(0, Math.min(1 - origBox.height, origBox.y + dy));

            onUpdateRegionBox?.(regionId, {
        x: Number(newX.toFixed(6)),
        y: Number(newY.toFixed(6)),
        width: origBox.width,
        height: origBox.height,
      });
    };

    const onPointerUp = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      document.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerup", onPointerUp);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  };

  const startResizeBox = (e: React.PointerEvent, regionId: string, currentBox: RegionBox, dir: string) => {
    e.stopPropagation();
    e.preventDefault();
    const startCoords = getNormCoords(e);
    const origBox = { ...currentBox };
    const minSize = 0.02;

    const onPointerMove = (ev: PointerEvent) => {
            const cur = getNormCoords(ev);
      const dx = cur.x - startCoords.x;
      const dy = cur.y - startCoords.y;

      let newX = origBox.x;
      let newY = origBox.y;
      let newW = origBox.width;
      let newH = origBox.height;

      if (dir.includes("w")) {
        const rightEdge = origBox.x + origBox.width;
        newX = Math.max(0, Math.min(rightEdge - minSize, origBox.x + dx));
        newW = rightEdge - newX;
      }
      if (dir.includes("e")) {
        const candRight = Math.min(1, Math.max(origBox.x + minSize, origBox.x + origBox.width + dx));
        newW = candRight - origBox.x;
      }
      if (dir.includes("n")) {
        const bottomEdge = origBox.y + origBox.height;
        newY = Math.max(0, Math.min(bottomEdge - minSize, origBox.y + dy));
        newH = bottomEdge - newY;
      }
      if (dir.includes("s")) {
        const candBottom = Math.min(1, Math.max(origBox.y + minSize, origBox.y + origBox.height + dy));
        newH = candBottom - origBox.y;
      }

            onUpdateRegionBox?.(regionId, {
        x: Number(newX.toFixed(6)),
        y: Number(newY.toFixed(6)),
        width: Number(newW.toFixed(6)),
        height: Number(newH.toFixed(6)),
      });
    };

    const onPointerUp = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      document.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerup", onPointerUp);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  };

  return (
    <div
      ref={containerRef}
      className={`relative w-full overflow-hidden rounded-2xl border border-border bg-black/90 shadow-inner ${
        isDrawing ? "cursor-crosshair" : ""
      }`}
      style={{ aspectRatio }}
      data-testid="media-container"
      onPointerDown={handlePointerDownContainer}
      onClick={() => {
        if (!isDrawing) onSelectRegion(null);
      }}
    >
      {isImage ? (
        <img
          src={sourceUrl ?? ""}
          alt={snapshot.media.filename || "Source image"}
          className="absolute inset-0 h-full w-full object-contain pointer-events-none select-none"
        />
      ) : (
        <video
          ref={videoRef}
          controls
          preload="metadata"
          src={sourceUrl ?? ""}
          className="absolute inset-0 h-full w-full object-contain"
          onTimeUpdate={(e) => onTimeUpdate(Math.round(e.currentTarget.currentTime * 1000))}
        />
      )}

      {previewUrl && (
        <img
          src={previewUrl}
          alt="Preview of the redacted result"
          data-testid="blur-preview"
          // For a video the bottom strip is left to the player's controls.
          style={isImage ? undefined : { clipPath: "inset(0 0 44px 0)" }}
          className="absolute inset-0 h-full w-full select-none object-contain pointer-events-none"
        />
      )}

      {/* Overlay layer for boxes and polygons */}
      <div className="absolute inset-0 pointer-events-none">
        {/* SVG layer for polygons */}
        <svg
          className="absolute inset-0 h-full w-full pointer-events-none"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          {renderedRegions.map(({ region, polygon }) => {
            if (!polygon || polygon.length === 0) return null;
            const isSelected = selectedRegionId === region.id;
            const catVar = getCategoryVar(region.category);
            const pointsStr = polygon.map((p) => `${p.x * 100},${p.y * 100}`).join(" ");

            return (
              <polygon
                key={`poly-${region.id}`}
                data-testid={`polygon-${region.id}`}
                points={pointsStr}
                strokeDasharray="4 2"
                style={{
                  stroke: catVar,
                  fill: isSelected
                    ? `color-mix(in srgb, ${catVar} 32%, transparent)`
                    : `color-mix(in srgb, ${catVar} 16%, transparent)`,
                }}
                className="pointer-events-auto cursor-pointer stroke-2 transition-colors"
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectRegion(region.id);
                }}
              />
            );
          })}
        </svg>

        {/* Live drawing preview */}
        {drawingPreview && (
          <div
            className="absolute border-2 border-dashed border-primary bg-primary/20 pointer-events-none"
            style={{
              left: `${drawingPreview.x * 100}%`,
              top: `${drawingPreview.y * 100}%`,
              width: `${drawingPreview.width * 100}%`,
              height: `${drawingPreview.height * 100}%`,
            }}
          />
        )}

        {/* Bounding box divs & labels */}
        {renderedRegions.map(({ region, box, polygon }) => {
          const isSelected = selectedRegionId === region.id;
          const catVar = getCategoryVar(region.category);
          const hasPolygon = Boolean(polygon && polygon.length > 0);

          if (hasPolygon) {
            return (
              <div
                key={`label-${region.id}`}
                style={{
                  position: "absolute",
                  left: `${box.x * 100}%`,
                  top: `${box.y * 100}%`,
                }}
                className="pointer-events-none z-10"
              >
                <span
                  className="rounded px-1 py-0.5 text-[10px] font-semibold shadow border whitespace-nowrap"
                  style={{
                    backgroundColor: "var(--background)",
                    color: catVar,
                    borderColor: `color-mix(in srgb, ${catVar} 45%, transparent)`,
                  }}
                >
                  {formatKind(region.kind)}
                </span>
              </div>
            );
          }

          const handles = [
            { dir: "nw", style: { top: -4, left: -4 }, cursor: "nwse-resize" },
            { dir: "n", style: { top: -4, left: "calc(50% - 4px)" }, cursor: "ns-resize" },
            { dir: "ne", style: { top: -4, right: -4 }, cursor: "nesw-resize" },
            { dir: "w", style: { top: "calc(50% - 4px)", left: -4 }, cursor: "ew-resize" },
            { dir: "e", style: { top: "calc(50% - 4px)", right: -4 }, cursor: "ew-resize" },
            { dir: "sw", style: { bottom: -4, left: -4 }, cursor: "nesw-resize" },
            { dir: "s", style: { bottom: -4, left: "calc(50% - 4px)" }, cursor: "ns-resize" },
            { dir: "se", style: { bottom: -4, right: -4 }, cursor: "nwse-resize" },
          ];

          return (
            <div
              key={`box-${region.id}`}
              data-testid={`box-${region.id}`}
              onClick={(e) => {
                e.stopPropagation();
                onSelectRegion(region.id);
              }}
              onPointerDown={(e) => {
                startDragBox(e, region.id, box);
              }}
              style={{
                position: "absolute",
                left: `${box.x * 100}%`,
                top: `${box.y * 100}%`,
                width: `${box.width * 100}%`,
                height: `${box.height * 100}%`,
                borderColor: catVar,
                backgroundColor: isSelected
                  ? `color-mix(in srgb, ${catVar} 32%, transparent)`
                  : `color-mix(in srgb, ${catVar} 16%, transparent)`,
                boxShadow: isSelected ? `0 0 0 2px ${catVar}` : undefined,
                cursor: isSelected ? "move" : "pointer",
              }}
              className="pointer-events-auto border-2 border-dashed transition-colors"
            >
              <span
                className="absolute -top-5 left-0 rounded px-1 py-0.5 text-[10px] font-semibold shadow border whitespace-nowrap pointer-events-none select-none"
                style={{
                  backgroundColor: "var(--background)",
                  color: catVar,
                  borderColor: `color-mix(in srgb, ${catVar} 45%, transparent)`,
                }}
              >
                {formatKind(region.kind)}
              </span>

              {/* 8 resize handles when selected */}
              {isSelected &&
                handles.map((h) => (
                  <div
                    key={h.dir}
                    data-testid={`handle-${h.dir}-${region.id}`}
                    style={{
                      position: "absolute",
                      width: 8,
                      height: 8,
                      backgroundColor: "var(--background)",
                      borderColor: catVar,
                      cursor: h.cursor,
                      ...h.style,
                    }}
                    className="rounded-xs border-2 z-20 pointer-events-auto shadow-sm"
                    onPointerDown={(e) => startResizeBox(e, region.id, box, h.dir)}
                  />
                ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ---------------- Video Timeline Bar ---------------- */

export function VideoTimeline({
  snapshot,
  currentTimeMs,
  onSeek,
  regions,
  onUpdateRegion,
}: {
  snapshot: Snapshot;
  currentTimeMs: number;
  onSeek: (ms: number) => void;
  regions?: MediaRegion[];
  onUpdateRegion?: (regionId: string, updates: Partial<MediaRegion>) => void;
}) {
  const durationMs = snapshot.media.duration_ms || 1;
  const currentPercent = Math.min(100, Math.max(0, (currentTimeMs / durationMs) * 100));
  const activeRegions = regions ?? snapshot.regions;
  const barRef = useRef<HTMLDivElement | null>(null);

  const formatMs = (ms: number) => {
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${m}:${rem.toString().padStart(2, "0")}`;
  };

  const handleTrimStart = (e: React.PointerEvent, r: MediaRegion) => {
    e.stopPropagation();
    e.preventDefault();
    if (!barRef.current) return;
    const rect = barRef.current.getBoundingClientRect();
    const origStart = r.start_ms;
    const origEnd = r.end_ms;
    const origX = e.clientX;

    const onPointerMove = (ev: PointerEvent) => {
            const dx = ev.clientX - origX;
      const dMs = (dx / (rect.width || 1)) * durationMs;
      const raw = origStart + dMs;
      const snapped = Math.round(raw / 100) * 100;
      const clamped = Math.max(0, Math.min(origEnd, snapped));
      onUpdateRegion?.(r.id, { start_ms: clamped });
    };

    const onPointerUp = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      document.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerup", onPointerUp);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  };

  const handleTrimEnd = (e: React.PointerEvent, r: MediaRegion) => {
    e.stopPropagation();
    e.preventDefault();
    if (!barRef.current) return;
    const rect = barRef.current.getBoundingClientRect();
    const origStart = r.start_ms;
    const origEnd = r.end_ms;
    const origX = e.clientX;

    const onPointerMove = (ev: PointerEvent) => {
            const dx = ev.clientX - origX;
      const dMs = (dx / (rect.width || 1)) * durationMs;
      const raw = origEnd + dMs;
      const snapped = Math.round(raw / 100) * 100;
      const clamped = Math.max(origStart, Math.min(durationMs, snapped));
      onUpdateRegion?.(r.id, { end_ms: clamped });
    };

    const onPointerUp = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      document.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerup", onPointerUp);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  };

  const handleShift = (e: React.PointerEvent, r: MediaRegion) => {
    e.stopPropagation();
    e.preventDefault();
    if (!barRef.current) return;
    const rect = barRef.current.getBoundingClientRect();
    const origStart = r.start_ms;
    const origEnd = r.end_ms;
    const origX = e.clientX;
    const span = origEnd - origStart;

    const onPointerMove = (ev: PointerEvent) => {
            const dx = ev.clientX - origX;
      const dMs = (dx / (rect.width || 1)) * durationMs;
      const raw = origStart + dMs;
      const snapped = Math.round(raw / 100) * 100;
      const clampedStart = Math.max(0, Math.min(durationMs - span, snapped));
      const clampedEnd = clampedStart + span;
      const delta = clampedStart - origStart;

      const shiftedKfs = r.keyframes.map((kf) => ({
        ...kf,
        time_ms: Math.max(0, Math.min(durationMs, kf.time_ms + delta)),
      }));

      onUpdateRegion?.(r.id, {
        start_ms: clampedStart,
        end_ms: clampedEnd,
        keyframes: shiftedKfs,
      });
    };

    const onPointerUp = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      document.removeEventListener("pointermove", onPointerMove);
      document.removeEventListener("pointerup", onPointerUp);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    document.addEventListener("pointermove", onPointerMove);
    document.addEventListener("pointerup", onPointerUp);
  };

  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-3" data-testid="video-timeline">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span className="font-medium text-foreground">Video timeline</span>
        <span className="tabular-nums">
          {formatMs(currentTimeMs)} / {formatMs(durationMs)}
        </span>
      </div>

      <div
        ref={barRef}
        className="relative h-16 w-full cursor-pointer rounded-lg bg-muted/70 p-2 overflow-hidden select-none"
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
          onSeek(Math.round(frac * durationMs));
        }}
      >
        {/* Playhead marker */}
        <div
          data-testid="playhead-marker"
          className="absolute top-0 bottom-0 z-20 w-0.5 bg-primary shadow-sm pointer-events-none"
          style={{ left: `${currentPercent}%` }}
        >
          <div className="absolute -top-1 -left-1.5 h-3.5 w-3.5 rounded-full bg-primary border-2 border-background" />
        </div>

        {/* Region tracks */}
        <div className="flex h-full flex-col justify-around gap-1">
          {activeRegions.map((region) => {
            const startPct = Math.max(0, (region.start_ms / durationMs) * 100);
            const endPct = Math.min(100, (region.end_ms / durationMs) * 100);
            const widthPct = Math.max(0.5, endPct - startPct);
            const catVar = getCategoryVar(region.category);

            return (
              <div key={`track-${region.id}`} className="relative h-2.5 w-full rounded bg-background/50">
                <div
                  data-testid={`span-track-${region.id}`}
                  className="absolute top-0 bottom-0 rounded border border-dashed opacity-90 flex items-center justify-between overflow-hidden"
                  style={{
                    left: `${startPct}%`,
                    width: `${widthPct}%`,
                    backgroundColor: `color-mix(in srgb, ${catVar} 35%, transparent)`,
                    borderColor: catVar,
                  }}
                  title={`${formatKind(region.kind)} (${formatMs(region.start_ms)} - ${formatMs(region.end_ms)})`}
                >
                  {/* Trim start handle */}
                  <div
                    data-testid={`trim-start-${region.id}`}
                    onPointerDown={(e) => handleTrimStart(e, region)}
                    className="h-full w-2 cursor-ew-resize bg-background/60 hover:bg-background z-10"
                    title="Trim start"
                  />

                  {/* Shift span */}
                  <div
                    data-testid={`span-shift-${region.id}`}
                    onPointerDown={(e) => handleShift(e, region)}
                    className="h-full flex-1 cursor-grab active:cursor-grabbing"
                    title="Shift span"
                  />

                  {/* Trim end handle */}
                  <div
                    data-testid={`trim-end-${region.id}`}
                    onPointerDown={(e) => handleTrimEnd(e, region)}
                    className="h-full w-2 cursor-ew-resize bg-background/60 hover:bg-background z-10"
                    title="Trim end"
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ---------------- Right Panel Regions List Grouped by Category ---------------- */

export function MediaRegionsList({
  regions,
  selectedRegionId,
  onSelectRegion,
  onUpdateRegion,
  onRemoveRegion,
  onTrackRegion,
  trackingRegionId,
  isAudioOrImage = false,
  durationMs = 0,
  validationErrors,
}: {
  regions: MediaRegion[];
  selectedRegionId: string | null;
  onSelectRegion: (id: string) => void;
  onUpdateRegion?: (id: string, updates: Partial<MediaRegion>) => void;
  onRemoveRegion?: (id: string) => void;
  onTrackRegion?: ((region: MediaRegion) => void) | undefined;
  trackingRegionId?: string | null;
  isAudioOrImage?: boolean;
  durationMs?: number;
  validationErrors?: Record<string, string>;
}) {
  const grouped = useMemo(() => {
    const map = new Map<string, MediaRegion[]>();
    for (const r of regions) {
      const list = map.get(r.category) ?? [];
      list.push(r);
      map.set(r.category, list);
    }
    return Array.from(map.entries());
  }, [regions]);

  if (regions.length === 0) {
    return (
      <div className="py-6 text-center text-sm text-muted-foreground">
        No sensitive regions detected.
      </div>
    );
  }

  const categoryOptions = [
    "identificacao",
    "biometrico",
    "saude",
    "financeiro",
    "genetico",
    "origem",
    "familia",
    "comportamento",
    "quasi",
  ];

  const kindOptions: RegionKind[] = [
    "face",
    "text",
    "identity_document",
    "plate",
    "signature",
    "biometric",
    "code",
    "other",
  ];

  return (
    <div className="space-y-4" data-testid="regions-grouped-list">
      {grouped.map(([cat, list]) => {
        const catVar = getCategoryVar(cat);

        return (
          <div key={cat} className="space-y-2">
            <div className="flex items-center justify-between border-b border-border pb-1">
              <h4
                className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider"
                style={{ color: catVar }}
              >
                <span
                  className="inline-block h-2 w-2 rounded-full border border-dashed"
                  style={{ backgroundColor: catVar, borderColor: catVar }}
                  aria-hidden
                />
                {categoryLabel(cat)}
              </h4>
              <span className="text-[11px] font-semibold text-muted-foreground">
                {list.length}
              </span>
            </div>

            <div className="space-y-2.5">
              {list.map((r) => {
                const isSelected = selectedRegionId === r.id;
                const rCatVar = getCategoryVar(r.category);
                const isInvalid = Boolean(validationErrors?.[r.id]);

                return (
                  <div
                    key={r.id}
                    data-testid={`region-item-${r.id}`}
                    onClick={() => onSelectRegion(r.id)}
                    style={
                      isSelected
                        ? {
                            borderColor: rCatVar,
                            backgroundColor: `color-mix(in srgb, ${rCatVar} 14%, transparent)`,
                            boxShadow: `0 0 0 1px ${rCatVar}`,
                          }
                        : undefined
                    }
                    className={`cursor-pointer rounded-lg border p-3 transition-all flex flex-col gap-2.5 ${
                      isSelected ? "" : "border-border bg-background hover:bg-muted/50"
                    }`}
                  >
                    {/* Line 1: kind label as plain text on the left, confidence badge on the right */}
                    <div className="flex items-center justify-between gap-2 min-w-0">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span
                          className="inline-block h-2 w-2 rounded-full border border-dashed shrink-0"
                          style={{ backgroundColor: rCatVar, borderColor: rCatVar }}
                          aria-hidden
                        />
                        <span className="text-xs font-semibold text-foreground truncate">
                          {formatKind(r.kind)}
                        </span>
                      </div>
                      <span
                        className="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium border border-dashed"
                        style={{
                          borderColor: `color-mix(in srgb, ${rCatVar} 45%, transparent)`,
                          backgroundColor: `color-mix(in srgb, ${rCatVar} 12%, transparent)`,
                          color: rCatVar,
                        }}
                      >
                        {formatConfidence(r.confidence)}
                      </span>
                    </div>

                    {/* Line 2: reason text */}
                    {r.reason ? (
                      <p className="text-xs text-muted-foreground line-clamp-2 break-words leading-relaxed">
                        {r.reason}
                      </p>
                    ) : null}

                    {/* Line 3: kind select and category select stacked vertically (full width each, small visible label) */}
                    {onUpdateRegion && (
                      <div className="flex flex-col gap-2 pt-1 border-t border-border/50">
                        <label className="flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
                          <span>Kind</span>
                          <select
                            value={r.kind}
                            aria-label="Region kind"
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) => onUpdateRegion(r.id, { kind: e.target.value as RegionKind })}
                            className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs font-medium text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                          >
                            {kindOptions.map((k) => (
                              <option key={k} value={k}>
                                {"\u200B" + formatKind(k)}
                              </option>
                            ))}
                          </select>
                        </label>

                        <label className="flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
                          <span>Category</span>
                          <select
                            value={r.category}
                            aria-label="Region category"
                            onClick={(e) => e.stopPropagation()}
                            onChange={(e) => onUpdateRegion(r.id, { category: e.target.value })}
                            className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs font-medium text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
                          >
                            {categoryOptions.map((c) => (
                              <option key={c} value={c}>
                                {"\u200B" + categoryLabel(c)}
                              </option>
                            ))}
                          </select>
                        </label>
                      </div>
                    )}

                    {/* For image: Remove button */}
                    {isAudioOrImage && onRemoveRegion && (
                      <div className="flex items-center justify-end pt-0.5">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          aria-label="Remove region"
                          className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive hover:border-destructive/40 gap-1.5"
                          onClick={(e) => {
                            e.stopPropagation();
                            onRemoveRegion(r.id);
                          }}
                        >
                          <Trash2 className="h-3 w-3" />
                          <span>Remove</span>
                        </Button>
                      </div>
                    )}

                    {/* For video: Start and End number inputs side by side on one row, then Track and Remove buttons on a row below */}
                    {!isAudioOrImage && (
                      <div className="flex flex-col gap-2 pt-1 border-t border-border/50">
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <label className="flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
                            <span>Start (s)</span>
                            <input
                              type="number"
                              step="0.1"
                              min="0"
                              max={durationMs ? (durationMs / 1000).toFixed(1) : undefined}
                              value={(r.start_ms / 1000).toFixed(1)}
                              aria-label="Start time in seconds"
                              onClick={(e) => e.stopPropagation()}
                              onChange={(e) => {
                                const val = parseFloat(e.target.value);
                                if (!isNaN(val)) {
                                  onUpdateRegion?.(r.id, { start_ms: Math.round(val * 1000) });
                                }
                              }}
                              className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs text-foreground tabular-nums focus:outline-none focus:ring-1 focus:ring-primary"
                            />
                          </label>

                          <label className="flex flex-col gap-1 text-[11px] font-medium text-muted-foreground">
                            <span>End (s)</span>
                            <input
                              type="number"
                              step="0.1"
                              min="0"
                              max={durationMs ? (durationMs / 1000).toFixed(1) : undefined}
                              value={(r.end_ms / 1000).toFixed(1)}
                              aria-label="End time in seconds"
                              onClick={(e) => e.stopPropagation()}
                              onChange={(e) => {
                                const val = parseFloat(e.target.value);
                                if (!isNaN(val)) {
                                  onUpdateRegion?.(r.id, { end_ms: Math.round(val * 1000) });
                                }
                              }}
                              className="w-full h-8 rounded-md border border-border bg-background px-2 text-xs text-foreground tabular-nums focus:outline-none focus:ring-1 focus:ring-primary"
                            />
                          </label>
                        </div>

                        {isInvalid && (
                          <p className="text-[11px] font-medium text-destructive" role="alert">
                            {validationErrors?.[r.id]}
                          </p>
                        )}

                        <div className="flex items-center gap-2 pt-0.5">
                          {onTrackRegion && (
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              className="h-8 flex-1 text-xs gap-1.5"
                              disabled={trackingRegionId === r.id}
                              onClick={(e) => {
                                e.stopPropagation();
                                onTrackRegion(r);
                              }}
                              title="Follows the box forwards and backwards from the current frame"
                            >
                              {trackingRegionId === r.id ? (
                                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Crosshair className="h-3.5 w-3.5" />
                              )}
                              Track
                            </Button>
                          )}

                          {onRemoveRegion && (
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              aria-label="Remove region"
                              className="h-8 px-2.5 text-xs text-muted-foreground hover:text-destructive hover:border-destructive/40 gap-1.5"
                              onClick={(e) => {
                                e.stopPropagation();
                                onRemoveRegion(r.id);
                              }}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                              <span>Remove</span>
                            </Button>
                          )}
                        </div>
                      </div>
                    )}

                    {/* Bottom: source (AI, Face detector, You) */}
                    <div className="pt-1.5 flex items-center justify-between text-[11px] text-muted-foreground border-t border-border/40">
                      <span className="flex items-center gap-1.5">
                        {r.source === "gemini" ? (
                          <Sparkles className="h-3 w-3 text-brand shrink-0" />
                        ) : r.source === "user" ? (
                          <User className="h-3 w-3 shrink-0" />
                        ) : (
                          <Shield className="h-3 w-3 shrink-0" />
                        )}
                        <span>{formatSource(r.source)}</span>
                      </span>

                      {isAudioOrImage && r.end_ms > 0 && (
                        <span className="tabular-nums">
                          {(r.start_ms / 1000).toFixed(1)}s - {(r.end_ms / 1000).toFixed(1)}s
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
