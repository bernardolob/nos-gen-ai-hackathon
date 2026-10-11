import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Move, Plus, Save, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

export type Box = { x: number; y: number; width: number; height: number };
export type Point = { x: number; y: number };
export type Keyframe = { time_ms: number; box: Box; polygon?: Point[] | null };
export type MediaRegion = {
  id: string;
  category: string;
  kind: string;
  reason: string;
  confidence: "certo" | "provavel" | "incerto";
  source: "gemini" | "face_detector" | "user";
  start_ms: number;
  end_ms: number;
  keyframes: Keyframe[];
};

export type MediaInfo = {
  source_url: string;
  output_url?: string;
  filename: string;
  width: number;
  height: number;
  duration_ms?: number;
};

type Props = {
  api: string;
  attempt: number;
  kind: "image" | "video";
  media: MediaInfo;
  regions: MediaRegion[];
  disabled?: boolean;
  onSave: (regions: MediaRegion[]) => Promise<void>;
  onChange?: (regions: MediaRegion[]) => void;
  onTrack?: (region: MediaRegion, seedTimeMs: number) => Promise<MediaRegion>;
};

type Gesture = {
  type: "draw" | "move" | "resize";
  id?: string;
  startX: number;
  startY: number;
  original?: Box;
};

const clamp = (value: number, min = 0, max = 1) => Math.min(max, Math.max(min, value));

function boxAt(region: MediaRegion, timeMs: number): Box | null {
  if (timeMs < region.start_ms || timeMs > region.end_ms) return null;
  const keys = [...region.keyframes].sort((a, b) => a.time_ms - b.time_ms);
  if (!keys.length) return null;
  const nextIndex = keys.findIndex((key) => key.time_ms >= timeMs);
  if (nextIndex === -1) return keys[keys.length - 1]?.box ?? null;
  if (nextIndex === 0) return keys[0]?.box ?? null;
  const left = keys[nextIndex - 1];
  const right = keys[nextIndex];
  if (!left || !right) return null;
  const ratio =
    right.time_ms === left.time_ms ? 0 : (timeMs - left.time_ms) / (right.time_ms - left.time_ms);
  return {
    x: left.box.x + (right.box.x - left.box.x) * ratio,
    y: left.box.y + (right.box.y - left.box.y) * ratio,
    width: left.box.width + (right.box.width - left.box.width) * ratio,
    height: left.box.height + (right.box.height - left.box.height) * ratio,
  };
}

function polygonAt(region: MediaRegion, timeMs: number): Point[] | null {
  if (timeMs < region.start_ms || timeMs > region.end_ms) return null;
  const keys = [...region.keyframes].sort((a, b) => a.time_ms - b.time_ms);
  if (!keys.length) return null;
  const nextIndex = keys.findIndex((key) => key.time_ms >= timeMs);
  if (nextIndex === -1) return keys[keys.length - 1]?.polygon ?? null;
  if (keys[nextIndex]?.time_ms === timeMs) return keys[nextIndex]?.polygon ?? null;
  if (nextIndex === 0) return keys[0]?.polygon ?? null;
  const left = keys[nextIndex - 1];
  const right = keys[nextIndex];
  if (!left?.polygon || !right?.polygon || left.polygon.length !== right.polygon.length)
    return null;
  const ratio =
    right.time_ms === left.time_ms ? 0 : (timeMs - left.time_ms) / (right.time_ms - left.time_ms);
  return left.polygon.map((point, index) => ({
    x: point.x + (right.polygon![index]!.x - point.x) * ratio,
    y: point.y + (right.polygon![index]!.y - point.y) * ratio,
  }));
}

function transformPolygon(polygon: Point[] | null, source: Box, target: Box): Point[] | null {
  if (!polygon) return null;
  return polygon.map((point) => ({
    x: clamp(target.x + ((point.x - source.x) / source.width) * target.width),
    y: clamp(target.y + ((point.y - source.y) / source.height) * target.height),
  }));
}

function withKeyframe(
  region: MediaRegion,
  timeMs: number,
  box: Box,
  polygon?: Point[] | null,
): MediaRegion {
  const keep = region.keyframes.filter((key) => Math.abs(key.time_ms - timeMs) > 60);
  return {
    ...region,
    keyframes: [...keep, { time_ms: timeMs, box, polygon: polygon ?? null }].sort(
      (a, b) => a.time_ms - b.time_ms,
    ),
  };
}

function paintPixelatedPreview(
  canvas: HTMLCanvasElement,
  source: HTMLImageElement | HTMLVideoElement,
  regions: MediaRegion[],
  timeMs: number,
  width: number,
  height: number,
): boolean {
  if (!width || !height) return false;
  const context = canvas.getContext("2d");
  if (!context) return false;
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  context.clearRect(0, 0, width, height);

  try {
    for (const region of regions) {
      const box = boxAt(region, timeMs);
      if (!box) continue;
      const left = Math.max(0, Math.round(box.x * width));
      const top = Math.max(0, Math.round(box.y * height));
      const right = Math.min(width, Math.round((box.x + box.width) * width));
      const bottom = Math.min(height, Math.round((box.y + box.height) * height));
      const areaWidth = right - left;
      const areaHeight = bottom - top;
      if (areaWidth < 1 || areaHeight < 1) continue;

      const coarse = document.createElement("canvas");
      const cellSize = Math.max(24, Math.ceil(Math.min(areaWidth, areaHeight) / 5));
      coarse.width = Math.max(1, Math.ceil(areaWidth / cellSize));
      coarse.height = Math.max(1, Math.ceil(areaHeight / cellSize));
      const coarseContext = coarse.getContext("2d");
      if (!coarseContext) return false;
      coarseContext.drawImage(
        source,
        left,
        top,
        areaWidth,
        areaHeight,
        0,
        0,
        coarse.width,
        coarse.height,
      );

      // Enlarging averaged cells with smoothing disabled gives a crisp mosaic.
      // The opaque cells also prevent the source image showing through.
      const polygon = polygonAt(region, timeMs);
      if (polygon) {
        context.save();
        context.beginPath();
        polygon.forEach((point, index) => {
          const x = point.x * width;
          const y = point.y * height;
          if (index === 0) context.moveTo(x, y);
          else context.lineTo(x, y);
        });
        context.closePath();
        context.clip();
      }
      context.imageSmoothingEnabled = false;
      context.fillStyle = "rgb(43, 69, 90)";
      context.fillRect(left, top, areaWidth, areaHeight);
      context.drawImage(coarse, left, top, areaWidth, areaHeight);
      context.fillStyle = "rgba(43, 69, 90, 0.22)";
      context.fillRect(left, top, areaWidth, areaHeight);
      if (polygon) context.restore();
    }
    return true;
  } catch {
    context.clearRect(0, 0, width, height);
    return false;
  }
}

export function MediaReview({
  api,
  attempt,
  kind,
  media,
  regions,
  disabled,
  onSave,
  onTrack,
  onChange,
}: Props) {
  const draft = regions;
  const setDraft = (value: MediaRegion[] | ((current: MediaRegion[]) => MediaRegion[])) => {
    onChange?.(typeof value === "function" ? value(draft) : value);
  };
  const [selected, setSelected] = useState<string | null>(null);
  const [timeMs, setTimeMs] = useState(0);
  const [gesture, setGesture] = useState<Gesture | null>(null);
  const [drawBox, setDrawBox] = useState<Box | null>(null);
  const [saving, setSaving] = useState(false);
  const [tracking, setTracking] = useState(false);
  const [trackError, setTrackError] = useState("");
  const [loaded, setLoaded] = useState(0);
  const [paintedSource, setPaintedSource] = useState<string | null>(null);
  const stage = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const previewRef = useRef<HTMLCanvasElement>(null);
  const attemptRef = useRef(attempt);

  useEffect(() => {
    attemptRef.current = attempt;
    setSelected(null);
  }, [attempt, media.source_url]);
  const selectedRegion = useMemo(
    () => draft.find((region) => region.id === selected) ?? null,
    [draft, selected],
  );
  const durationMs = media.duration_ms ?? 0;
  const source = media.source_url.startsWith("data:")
    ? media.source_url
    : `${api}${media.source_url}?attempt=${attempt}`;
  const previewReady = paintedSource === source;

  useLayoutEffect(() => {
    const canvas = previewRef.current;
    const element = kind === "image" ? imageRef.current : videoRef.current;
    if (!canvas || !element) return;
    const paint = () => {
      const width =
        kind === "image"
          ? (imageRef.current?.naturalWidth ?? 0)
          : (videoRef.current?.videoWidth ?? 0);
      const height =
        kind === "image"
          ? (imageRef.current?.naturalHeight ?? 0)
          : (videoRef.current?.videoHeight ?? 0);
      const position =
        kind === "image"
          ? 0
          : Math.min(durationMs, Math.round((videoRef.current?.currentTime ?? 0) * 1000));
      const ready = paintPixelatedPreview(canvas, element, draft, position, width, height);
      setPaintedSource((current) => (ready ? source : current === source ? null : current));
    };
    paint();
    return undefined;
  }, [kind, source, draft, loaded, timeMs, durationMs]);

  useEffect(() => {
    if (kind !== "video") return;
    const video = videoRef.current;
    if (!video) return;
    let frameHandle: number | null = null;
    let animationHandle: number | null = null;
    const sync = (mediaTime = video.currentTime) => {
      setTimeMs(Math.min(durationMs, Math.max(0, Math.round(mediaTime * 1000))));
    };
    const schedule = () => {
      if (frameHandle !== null || animationHandle !== null) return;
      if (typeof video.requestVideoFrameCallback === "function") {
        frameHandle = video.requestVideoFrameCallback((_now, metadata) => {
          frameHandle = null;
          sync(metadata.mediaTime);
          if (!video.paused && !video.ended) schedule();
        });
      } else {
        animationHandle = requestAnimationFrame(() => {
          animationHandle = null;
          sync();
          if (!video.paused && !video.ended) schedule();
        });
      }
    };
    const start = () => {
      sync();
      schedule();
    };
    const stop = () => {
      sync();
    };
    video.addEventListener("play", start);
    video.addEventListener("loadeddata", start);
    video.addEventListener("seeked", stop);
    video.addEventListener("pause", stop);
    if (!video.paused) schedule();
    return () => {
      if (frameHandle !== null && typeof video.cancelVideoFrameCallback === "function")
        video.cancelVideoFrameCallback(frameHandle);
      if (animationHandle !== null) cancelAnimationFrame(animationHandle);
      video.removeEventListener("play", start);
      video.removeEventListener("loadeddata", start);
      video.removeEventListener("seeked", stop);
      video.removeEventListener("pause", stop);
    };
  }, [kind, durationMs, loaded]);

  function point(event: React.PointerEvent): [number, number] {
    const bounds = stage.current?.getBoundingClientRect();
    if (!bounds) return [0, 0];
    return [
      clamp((event.clientX - bounds.left) / bounds.width),
      clamp((event.clientY - bounds.top) / bounds.height),
    ];
  }

  function startDraw(event: React.PointerEvent) {
    if (disabled || (event.target as HTMLElement).closest(".redaction-region")) return;
    const [x, y] = point(event);
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setSelected(null);
    setGesture({ type: "draw", startX: x, startY: y });
    setDrawBox({ x, y, width: 0.001, height: 0.001 });
  }

  function startEdit(event: React.PointerEvent, id: string, type: "move" | "resize") {
    if (disabled) return;
    event.stopPropagation();
    if (videoRef.current && !videoRef.current.paused) {
      videoRef.current.pause();
      setTimeMs(Math.min(durationMs, Math.round(videoRef.current.currentTime * 1000)));
    }
    const region = draft.find((item) => item.id === id);
    const original = region ? boxAt(region, timeMs) : null;
    if (!original) return;
    const [x, y] = point(event);
    event.currentTarget.setPointerCapture?.(event.pointerId);
    setSelected(id);
    setGesture({ type, id, startX: x, startY: y, original });
  }

  function move(event: React.PointerEvent) {
    if (!gesture) return;
    const [x, y] = point(event);
    if (gesture.type === "draw") {
      setDrawBox({
        x: Math.min(x, gesture.startX),
        y: Math.min(y, gesture.startY),
        width: Math.abs(x - gesture.startX),
        height: Math.abs(y - gesture.startY),
      });
      return;
    }
    if (!gesture.id || !gesture.original) return;
    const dx = x - gesture.startX;
    const dy = y - gesture.startY;
    const original = gesture.original;
    const box =
      gesture.type === "move"
        ? {
            ...original,
            x: clamp(original.x + dx, 0, 1 - original.width),
            y: clamp(original.y + dy, 0, 1 - original.height),
          }
        : {
            ...original,
            width: clamp(original.width + dx, 0.01, 1 - original.x),
            height: clamp(original.height + dy, 0.01, 1 - original.y),
          };
    setDraft((current) =>
      current.map((region) => {
        if (region.id !== gesture.id) return region;
        const polygon = transformPolygon(polygonAt(region, timeMs), original, box);
        return withKeyframe(region, timeMs, box, polygon);
      }),
    );
  }

  async function trackRegion(region: MediaRegion, seedTime = timeMs) {
    if (!onTrack || kind !== "video") return;
    const requestAttempt = attempt;
    setTracking(true);
    setTrackError("");
    try {
      const tracked = await onTrack(region, seedTime);
      if (attemptRef.current !== requestAttempt) return;
      setDraft((current) => current.map((item) => (item.id === region.id ? tracked : item)));
    } catch (error) {
      setTrackError(error instanceof Error ? error.message : "Não foi possível rastrear a caixa.");
    } finally {
      setTracking(false);
    }
  }

  function finish() {
    if (gesture?.type === "draw" && drawBox && drawBox.width >= 0.01 && drawBox.height >= 0.01) {
      const id = crypto.randomUUID();
      const region: MediaRegion = {
        id,
        category: "identificacao",
        kind: "other",
        reason: "Region added manually by the reviewer.",
        confidence: "certo",
        source: "user",
        start_ms: kind === "video" ? 0 : 0,
        end_ms: kind === "video" ? durationMs : 0,
        keyframes: [{ time_ms: kind === "video" ? timeMs : 0, box: drawBox }],
      };
      setDraft((current) => [...current, region]);
      setSelected(id);
      void trackRegion(region);
    }
    setGesture(null);
    setDrawBox(null);
  }

  function removeSelected() {
    if (!selectedRegion) return;
    setDraft((current) => current.filter((region) => region.id !== selectedRegion.id));
    setSelected(null);
  }

  async function save() {
    setSaving(true);
    try {
      await onSave(draft);
    } finally {
      setSaving(false);
    }
  }

  function addKeyframe() {
    if (!selectedRegion) return;
    const box =
      boxAt(selectedRegion, timeMs) ??
      selectedRegion.keyframes.reduce((closest, keyframe) =>
        Math.abs(keyframe.time_ms - timeMs) < Math.abs(closest.time_ms - timeMs)
          ? keyframe
          : closest,
      ).box;
    const polygon = polygonAt(selectedRegion, timeMs);
    setDraft((current) =>
      current.map((region) =>
        region.id === selectedRegion.id ? withKeyframe(region, timeMs, box, polygon) : region,
      ),
    );
  }

  function seek(time: number) {
    const next = clamp(time, 0, durationMs);
    setTimeMs(next);
    if (videoRef.current) videoRef.current.currentTime = next / 1000;
  }

  function setBoundary(field: "start_ms" | "end_ms", seconds: number) {
    if (!selectedRegion) return;
    const value = clamp(seconds * 1000, 0, durationMs);
    setDraft((current) =>
      current.map((region) =>
        region.id === selectedRegion.id
          ? {
              ...region,
              [field]:
                field === "start_ms"
                  ? Math.min(value, region.end_ms)
                  : Math.max(value, region.start_ms),
            }
          : region,
      ),
    );
  }

  return (
    <div className="media-editor">
      <div
        className="media-stage"
        ref={stage}
        style={{
          aspectRatio: `${media.width} / ${media.height}`,
          maxWidth: `${Math.min(media.width, (650 * media.width) / media.height)}px`,
        }}
        onPointerDown={startDraw}
        onPointerMove={move}
        onPointerUp={finish}
        onPointerCancel={finish}
      >
        {kind === "image" ? (
          <img
            ref={imageRef}
            src={source}
            crossOrigin="anonymous"
            onLoad={() => setLoaded((value) => value + 1)}
            alt="Image under review"
            draggable={false}
          />
        ) : (
          <video
            ref={videoRef}
            src={source}
            crossOrigin="anonymous"
            controls
            playsInline
            onLoadedData={() => setLoaded((value) => value + 1)}
          />
        )}
        <canvas ref={previewRef} className="redaction-preview" aria-hidden="true" />
        <div className="region-layer" aria-label="Masked regions">
          {draft.map((region) => {
            const box = boxAt(region, timeMs);
            if (!box) return null;
            const polygon = polygonAt(region, timeMs);
            const polygonPoints = polygon
              ?.map(
                (point) =>
                  `${((point.x - box.x) / box.width) * 100},${((point.y - box.y) / box.height) * 100}`,
              )
              .join(" ");
            return (
              <div
                key={region.id}
                className={`redaction-region ${polygon ? "polygon" : ""} ${selected === region.id ? "selected" : ""} ${previewReady ? "" : "pending"}`}
                data-label={region.kind === "face" ? "FACE · PIXELATED" : "DATA · PIXELATED"}
                style={{
                  left: `${box.x * 100}%`,
                  top: `${box.y * 100}%`,
                  width: `${box.width * 100}%`,
                  height: `${box.height * 100}%`,
                }}
                onPointerDown={(event) => startEdit(event, region.id, "move")}
                title={`${region.kind}: ${region.reason}`}
              >
                {polygonPoints && (
                  <svg
                    className="region-polygon"
                    viewBox="0 0 100 100"
                    preserveAspectRatio="none"
                    aria-hidden="true"
                  >
                    <polygon points={polygonPoints} />
                  </svg>
                )}
                {selected === region.id && (
                  <button
                    className="region-handle"
                    aria-label="Resize mask"
                    onPointerDown={(event) => startEdit(event, region.id, "resize")}
                  />
                )}
              </div>
            );
          })}
          {drawBox && (
            <div
              className="redaction-region drawing"
              style={{
                left: `${drawBox.x * 100}%`,
                top: `${drawBox.y * 100}%`,
                width: `${drawBox.width * 100}%`,
                height: `${drawBox.height * 100}%`,
              }}
            />
          )}
        </div>
      </div>
      {kind === "video" && (
        <div className="keyframe-timeline">
          <input
            aria-label="Instante do vídeo"
            type="range"
            min={0}
            max={Math.max(1, durationMs)}
            step={1}
            value={timeMs}
            onChange={(event) => seek(Number(event.target.value))}
          />
          <div className="keyframe-markers" aria-label="Fotogramas-chave">
            {(selectedRegion?.keyframes ?? []).map((keyframe) => (
              <button
                key={keyframe.time_ms}
                type="button"
                aria-label={`Ir para fotograma-chave ${(keyframe.time_ms / 1000).toFixed(2)} s`}
                style={{ left: `${durationMs ? (keyframe.time_ms / durationMs) * 100 : 0}%` }}
                onClick={() => seek(keyframe.time_ms)}
              />
            ))}
          </div>
          <small>
            {(timeMs / 1000).toFixed(2)} s / {(durationMs / 1000).toFixed(2)} s
            {selectedRegion ? ` · ${selectedRegion.keyframes.length} fotogramas-chave` : ""}
          </small>
        </div>
      )}
      <div className="media-tools">
        <div>
          <strong>{draft.length} masks</strong>
          <small>
            <Move size={12} />
            Drag to add, move or resize masks
          </small>
        </div>
        <div className="media-tool-actions">
          {selectedRegion && kind === "video" && (
            <Button
              variant="outline"
              size="sm"
              onClick={addKeyframe}
              disabled={disabled || tracking}
            >
              <Plus />
              Fotograma-chave
            </Button>
          )}
          {selectedRegion && kind === "video" && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => void trackRegion(selectedRegion)}
              disabled={disabled || tracking}
            >
              <Move />
              {tracking ? "A rastrear…" : "Rastrear caixa"}
            </Button>
          )}
          {selectedRegion && (
            <Button
              variant="outline"
              size="sm"
              onClick={removeSelected}
              disabled={disabled || tracking}
            >
              <Trash2 />
              Remove mask
            </Button>
          )}
          <Button size="sm" onClick={save} disabled={disabled || saving}>
            <Save />
            {saving ? "Saving…" : "Save masks"}
          </Button>
        </div>
      </div>
      {trackError && (
        <p className="media-track-error" role="alert">
          {trackError}
        </p>
      )}
      {selectedRegion && (
        <div className="region-inspector">
          <div>
            <span>Type</span>
            <strong>{selectedRegion.kind}</strong>
          </div>
          <div>
            <span>Category</span>
            <strong>{selectedRegion.category}</strong>
          </div>
          <div>
            <span>Source</span>
            <strong>{selectedRegion.source}</strong>
          </div>
          <p>{selectedRegion.reason}</p>
          {kind === "video" && (
            <div className="region-times">
              <label>
                Início (s)
                <input
                  type="number"
                  min={0}
                  max={durationMs / 1000}
                  step="0.1"
                  value={(selectedRegion.start_ms / 1000).toFixed(1)}
                  onChange={(event) => setBoundary("start_ms", Number(event.target.value))}
                />
              </label>
              <label>
                Fim (s)
                <input
                  type="number"
                  min={0}
                  max={durationMs / 1000}
                  step="0.1"
                  value={(selectedRegion.end_ms / 1000).toFixed(1)}
                  onChange={(event) => setBoundary("end_ms", Number(event.target.value))}
                />
              </label>
            </div>
          )}
        </div>
      )}
      <p className="media-add-note">
        <Plus size={12} />
        Masks are pixelated in the exported document.
      </p>
    </div>
  );
}
