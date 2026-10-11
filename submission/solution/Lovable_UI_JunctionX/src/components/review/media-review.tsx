import { useMemo } from "react";
import { Check, Shield, User, Sparkles } from "lucide-react";

import type {
  Confidence,
  MediaRegion,
  RegionKeyframe,
  RegionKind,
  RegionSource,
  Snapshot,
} from "@/lib/review/types";
import { mediaSourceUrl } from "@/lib/review/api";

export const CATEGORY_LABELS: Record<string, string> = {
  identificacao: "Personal identification",
  biometrico: "Biometric",
  saude: "Health",
  financeiro: "Financial",
  genetico: "Genetic",
  origem_religiao_politica: "Origin, religion, politics or orientation",
  familia: "Family life",
  comportamento: "Personal behaviour",
  quasi_identificador: "Quasi-identifiers",
};

export const categoryLabel = (cat: string): string => CATEGORY_LABELS[cat] ?? cat;

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

export function getCategoryClasses(category: string, isSelected: boolean) {
  switch (category) {
    case "identificacao":
      return {
        box: isSelected
          ? "border-primary bg-primary/30 ring-2 ring-primary"
          : "border-primary/80 bg-primary/15 hover:bg-primary/25",
        text: "text-primary",
        border: "border-primary/40",
        polygon: isSelected ? "fill-primary/30 stroke-primary" : "fill-primary/15 stroke-primary/80 hover:fill-primary/25",
      };
    case "biometrico":
      return {
        box: isSelected
          ? "border-secondary-foreground bg-accent/40 ring-2 ring-primary"
          : "border-border bg-accent/20 hover:bg-accent/30",
        text: "text-foreground",
        border: "border-border",
        polygon: isSelected ? "fill-foreground/20 stroke-foreground" : "fill-foreground/10 stroke-foreground/70",
      };
    case "saude":
      return {
        box: isSelected
          ? "border-destructive bg-destructive/30 ring-2 ring-destructive"
          : "border-destructive/80 bg-destructive/15 hover:bg-destructive/25",
        text: "text-destructive",
        border: "border-destructive/40",
        polygon: isSelected ? "fill-destructive/30 stroke-destructive" : "fill-destructive/15 stroke-destructive/80",
      };
    case "financeiro":
      return {
        box: isSelected
          ? "border-ok bg-ok/30 ring-2 ring-ok"
          : "border-ok/80 bg-ok/15 hover:bg-ok/25",
        text: "text-ok",
        border: "border-ok/40",
        polygon: isSelected ? "fill-ok/30 stroke-ok" : "fill-ok/15 stroke-ok/80",
      };
    default:
      return {
        box: isSelected
          ? "border-primary bg-primary/30 ring-2 ring-primary"
          : "border-primary/70 bg-primary/15 hover:bg-primary/25",
        text: "text-primary",
        border: "border-primary/30",
        polygon: isSelected ? "fill-primary/30 stroke-primary" : "fill-primary/15 stroke-primary/70",
      };
  }
}

/**
 * Returns the keyframe that should be drawn for a region at currentTimeMs.
 * For images: keyframes[0].
 * For videos: latest keyframe where time_ms <= currentTimeMs, only if start_ms <= currentTimeMs <= end_ms.
 */
export function getActiveKeyframe(
  region: MediaRegion,
  currentTimeMs: number,
  isImage: boolean,
): RegionKeyframe | null {
  if (!region.keyframes || region.keyframes.length === 0) return null;
  if (isImage) {
    return region.keyframes[0] ?? null;
  }

  if (currentTimeMs < region.start_ms || currentTimeMs > region.end_ms) {
    return null;
  }

  const valid = region.keyframes.filter((kf) => kf.time_ms <= currentTimeMs);
  if (valid.length === 0) {
    return region.keyframes[0] ?? null;
  }

  return valid.reduce((latest, current) =>
    current.time_ms > latest.time_ms ? current : latest,
  );
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

  const regionsWithKeyframe = useMemo(() => {
    return snapshot.regions
      .map((region) => {
        const kf = getActiveKeyframe(region, currentTimeMs, isImage);
        return kf ? { region, kf } : null;
      })
      .filter((item): item is { region: MediaRegion; kf: RegionKeyframe } => item !== null);
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
        {/* SVG layer for any polygons */}
        <svg
          className="absolute inset-0 h-full w-full pointer-events-none"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
        >
          {regionsWithKeyframe.map(({ region, kf }) => {
            if (!kf.polygon || kf.polygon.length === 0) return null;
            const isSelected = selectedRegionId === region.id;
            const styles = getCategoryClasses(region.category, isSelected);
            const pointsStr = kf.polygon.map((p) => `${p.x * 100},${p.y * 100}`).join(" ");

            return (
              <polygon
                key={`poly-${region.id}`}
                data-testid={`polygon-${region.id}`}
                points={pointsStr}
                strokeDasharray="4 2"
                className={`pointer-events-auto cursor-pointer transition-colors stroke-2 ${styles.polygon}`}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectRegion(region.id);
                }}
              />
            );
          })}
        </svg>

        {/* Box divs & labels */}
        {regionsWithKeyframe.map(({ region, kf }) => {
          const isSelected = selectedRegionId === region.id;
          const styles = getCategoryClasses(region.category, isSelected);
          const hasPolygon = Boolean(kf.polygon && kf.polygon.length > 0);

          if (hasPolygon) {
            // Polygon is drawn in the SVG above; show the label near top-left of box
            return (
              <div
                key={`label-${region.id}`}
                style={{
                  position: "absolute",
                  left: `${kf.box.x * 100}%`,
                  top: `${kf.box.y * 100}%`,
                }}
                className="pointer-events-none z-10"
              >
                <span className="rounded bg-background/90 px-1 py-0.5 text-[10px] font-semibold text-foreground shadow border border-border">
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
                left: `${kf.box.x * 100}%`,
                top: `${kf.box.y * 100}%`,
                width: `${kf.box.width * 100}%`,
                height: `${kf.box.height * 100}%`,
              }}
              className={`pointer-events-auto cursor-pointer border-2 border-dashed transition-all ${styles.box}`}
            >
              <span className="absolute -top-5 left-0 rounded bg-background/90 px-1 py-0.5 text-[10px] font-semibold text-foreground shadow border border-border whitespace-nowrap pointer-events-none">
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
            const styles = getCategoryClasses(region.category, false);

            return (
              <div key={`track-${region.id}`} className="relative h-2 w-full rounded bg-background/50">
                <div
                  className={`absolute top-0 bottom-0 rounded ${styles.box} opacity-90`}
                  style={{
                    left: `${startPct}%`,
                    width: `${widthPct}%`,
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
      {grouped.map(([cat, list]) => (
        <div key={cat} className="space-y-2">
          <div className="flex items-center justify-between border-b border-border pb-1">
            <h4 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              {categoryLabel(cat)}
            </h4>
            <span className="text-[11px] font-semibold text-muted-foreground">
              {list.length}
            </span>
          </div>

          <div className="space-y-1.5">
            {list.map((r) => {
              const isSelected = selectedRegionId === r.id;
              const styles = getCategoryClasses(r.category, isSelected);

              return (
                <div
                  key={r.id}
                  data-testid={`region-item-${r.id}`}
                  onClick={() => onSelectRegion(r.id)}
                  className={`cursor-pointer rounded-lg border p-2.5 transition-all ${
                    isSelected
                      ? "border-primary bg-primary/10 ring-1 ring-primary shadow-sm"
                      : "border-border bg-background hover:bg-muted/50"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-sm font-semibold text-foreground">
                      {formatKind(r.kind)}
                    </span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[10px] font-medium border ${
                        r.confidence === "certo"
                          ? "border-ok/40 bg-ok/10 text-ok"
                          : r.confidence === "provavel"
                          ? "border-warn/40 bg-warn/10 text-warn"
                          : "border-border bg-muted text-muted-foreground"
                      }`}
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
      ))}
    </div>
  );
}
