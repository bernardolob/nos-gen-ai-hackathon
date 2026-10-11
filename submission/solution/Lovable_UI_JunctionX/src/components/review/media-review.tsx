import { useEffect, useMemo } from "react";
import { Shield, User, Sparkles } from "lucide-react";

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

/* ---------------- Media Center Card Viewer ---------------- */

export function MediaViewer({
  snapshot,
  currentTimeMs,
  onTimeUpdate,
  selectedRegionId,
  onSelectRegion,
  videoRef,
}: {
  snapshot: Snapshot;
  currentTimeMs: number;
  onTimeUpdate: (ms: number) => void;
  selectedRegionId: string | null;
  onSelectRegion: (id: string) => void;
  videoRef?: React.RefObject<HTMLVideoElement | null>;
}) {
  const isImage = snapshot.kind === "image";
  const sourceUrl = mediaSourceUrl(snapshot);

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

  const renderedRegions = useMemo(() => {
    return snapshot.regions
      .map((region) => {
        const active = getActiveRenderRegion(region, currentTimeMs, isImage);
        return active ? { region, ...active } : null;
      })
      .filter((item): item is { region: MediaRegion; box: RegionBox; polygon: RegionPoint[] | null } => item !== null);
  }, [snapshot.regions, currentTimeMs, isImage]);

  return (
    <div
      className="relative w-full overflow-hidden rounded-2xl border border-border bg-black/90 shadow-inner"
      style={{ aspectRatio }}
      data-testid="media-container"
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

          return (
            <div
              key={`box-${region.id}`}
              data-testid={`box-${region.id}`}
              onClick={(e) => {
                e.stopPropagation();
                onSelectRegion(region.id);
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
              }}
              className="pointer-events-auto cursor-pointer border-2 border-dashed transition-all"
            >
              <span
                className="absolute -top-5 left-0 rounded px-1 py-0.5 text-[10px] font-semibold shadow border whitespace-nowrap pointer-events-none"
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
}: {
  snapshot: Snapshot;
  currentTimeMs: number;
  onSeek: (ms: number) => void;
}) {
  const durationMs = snapshot.media.duration_ms || 1;
  const currentPercent = Math.min(100, Math.max(0, (currentTimeMs / durationMs) * 100));

  const formatMs = (ms: number) => {
    const s = Math.floor(ms / 1000);
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${m}:${rem.toString().padStart(2, "0")}`;
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
          className="absolute top-0 bottom-0 z-20 w-0.5 bg-primary shadow-sm"
          style={{ left: `${currentPercent}%` }}
        >
          <div className="absolute -top-1 -left-1.5 h-3.5 w-3.5 rounded-full bg-primary border-2 border-background" />
        </div>

        {/* Region tracks */}
        <div className="flex h-full flex-col justify-around gap-1">
          {snapshot.regions.map((region) => {
            const startPct = Math.max(0, (region.start_ms / durationMs) * 100);
            const endPct = Math.min(100, (region.end_ms / durationMs) * 100);
            const widthPct = Math.max(0.5, endPct - startPct);
            const catVar = getCategoryVar(region.category);

            return (
              <div key={`track-${region.id}`} className="relative h-2 w-full rounded bg-background/50">
                <div
                  className="absolute top-0 bottom-0 rounded border border-dashed opacity-90"
                  style={{
                    left: `${startPct}%`,
                    width: `${widthPct}%`,
                    backgroundColor: `color-mix(in srgb, ${catVar} 35%, transparent)`,
                    borderColor: catVar,
                  }}
                  title={`${formatKind(region.kind)} (${formatMs(region.start_ms)} - ${formatMs(region.end_ms)})`}
                />
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
}: {
  regions: MediaRegion[];
  selectedRegionId: string | null;
  onSelectRegion: (id: string) => void;
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

            <div className="space-y-1.5">
              {list.map((r) => {
                const isSelected = selectedRegionId === r.id;
                const rCatVar = getCategoryVar(r.category);

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
                    className={`cursor-pointer rounded-lg border p-2.5 transition-all ${
                      isSelected
                        ? ""
                        : "border-border bg-background hover:bg-muted/50"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
                        <span
                          className="inline-block h-2 w-2 rounded-full border border-dashed"
                          style={{ backgroundColor: rCatVar, borderColor: rCatVar }}
                          aria-hidden
                        />
                        {formatKind(r.kind)}
                      </span>
                      <span
                        className="rounded px-1.5 py-0.5 text-[10px] font-medium border border-dashed"
                        style={{
                          borderColor: `color-mix(in srgb, ${rCatVar} 45%, transparent)`,
                          backgroundColor: `color-mix(in srgb, ${rCatVar} 12%, transparent)`,
                          color: rCatVar,
                        }}
                      >
                        {formatConfidence(r.confidence)}
                      </span>
                    </div>

                    {r.reason && (
                      <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
                        {r.reason}
                      </p>
                    )}

                    <div className="mt-2 flex items-center justify-between text-[11px] text-muted-foreground">
                      <span className="flex items-center gap-1">
                        {r.source === "gemini" ? (
                          <Sparkles className="h-3 w-3 text-brand" />
                        ) : r.source === "user" ? (
                          <User className="h-3 w-3" />
                        ) : (
                          <Shield className="h-3 w-3" />
                        )}
                        {formatSource(r.source)}
                      </span>

                      {r.end_ms > 0 && (
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
