import { useLayoutEffect, useRef, useState, type RefObject } from "react";
import type { MediaRegion } from "@/lib/review/types";
import { createPixelatedPreview } from "@/lib/review/media-preview";

export function useMediaPreview({
  sourceKey,
  isImage,
  enabled,
  regions,
  currentTimeMs,
  onTimeUpdate,
  imageRef,
  videoRef,
  canvasRef,
}: {
  sourceKey: string;
  isImage: boolean;
  enabled: boolean;
  regions: MediaRegion[];
  currentTimeMs: number;
  onTimeUpdate: (ms: number) => void;
  imageRef: RefObject<HTMLImageElement | null>;
  videoRef: RefObject<HTMLVideoElement | null>;
  canvasRef: RefObject<HTMLCanvasElement | null>;
}) {
  const [result, setResult] = useState({ key: "", ready: false, error: null as string | null });
  const latest = useRef({ enabled, regions, onTimeUpdate });
  const paintRef = useRef<((timeMs?: number) => void) | null>(null);
  const frameTime = useRef(0);

  useLayoutEffect(() => {
    latest.current = { enabled, regions, onTimeUpdate };
  });

  useLayoutEffect(() => {
    const source = isImage ? imageRef.current : videoRef.current;
    const canvas = canvasRef.current;
    if (!source || !canvas) return;
    const renderer = createPixelatedPreview();
    let disposed = false;
    let frameHandle: number | null = null;
    let animationHandle: number | null = null;
    const video = isImage ? null : videoRef.current;
    canvas.width = 0;
    frameTime.current = 0;

    const report = (ready: boolean, error: string | null = null) => {
      if (disposed) return;
      setResult((previous) =>
        previous.key === sourceKey && previous.ready === ready && previous.error === error
          ? previous
          : { key: sourceKey, ready, error },
      );
    };
    const paint = (timeMs = video ? Math.round(video.currentTime * 1000) : 0) => {
      if (disposed) return;
      frameTime.current = timeMs;
      if (!latest.current.enabled) {
        canvas.width = 0;
        report(false);
        return;
      }
      const width = isImage ? (imageRef.current?.naturalWidth ?? 0) : (video?.videoWidth ?? 0);
      const height = isImage ? (imageRef.current?.naturalHeight ?? 0) : (video?.videoHeight ?? 0);
      if (!width || !height || (video && video.readyState < 2)) {
        canvas.width = 0;
        report(false);
        return;
      }
      try {
        renderer(canvas, source, latest.current.regions, timeMs, width, height, isImage);
        report(true);
      } catch {
        canvas.width = 0;
        report(
          false,
          "Could not draw the censorship preview. Regions are covered with solid masks.",
        );
      }
    };
    paintRef.current = paint;

    const cancel = () => {
      if (frameHandle !== null && typeof video?.cancelVideoFrameCallback === "function") {
        video.cancelVideoFrameCallback(frameHandle);
      }
      if (animationHandle !== null) cancelAnimationFrame(animationHandle);
      frameHandle = animationHandle = null;
    };
    const schedule = () => {
      if (
        !video ||
        disposed ||
        video.paused ||
        video.ended ||
        frameHandle !== null ||
        animationHandle !== null
      )
        return;
      if (typeof video.requestVideoFrameCallback === "function") {
        frameHandle = video.requestVideoFrameCallback((_now, metadata) => {
          frameHandle = null;
          if (disposed) return;
          const time = Math.round(metadata.mediaTime * 1000);
          paint(time);
          latest.current.onTimeUpdate(time);
          schedule();
        });
      } else {
        animationHandle = requestAnimationFrame(() => {
          animationHandle = null;
          if (disposed) return;
          paint();
          latest.current.onTimeUpdate(frameTime.current);
          schedule();
        });
      }
    };
    const sync = () => {
      paint();
      if (video) latest.current.onTimeUpdate(frameTime.current);
    };
    const start = () => {
      sync();
      schedule();
    };
    const stop = () => {
      cancel();
      sync();
    };
    const loadError = () => {
      cancel();
      canvas.width = 0;
      report(false, "Could not load the media. Regions are covered with solid masks.");
    };
    source.addEventListener("error", loadError);
    source.addEventListener(isImage ? "load" : "loadeddata", start);
    video?.addEventListener("play", start);
    video?.addEventListener("seeked", sync);
    video?.addEventListener("pause", stop);
    video?.addEventListener("ended", stop);
    // A seek invalidates the old frame; cover regions until the new frame arrives.
    const seeking = () => {
      canvas.width = 0;
      report(false);
    };
    video?.addEventListener("seeking", seeking);
    paint();
    schedule();
    return () => {
      disposed = true;
      cancel();
      paintRef.current = null;
      source.removeEventListener("error", loadError);
      source.removeEventListener(isImage ? "load" : "loadeddata", start);
      video?.removeEventListener("play", start);
      video?.removeEventListener("seeked", sync);
      video?.removeEventListener("pause", stop);
      video?.removeEventListener("ended", stop);
      video?.removeEventListener("seeking", seeking);
      canvas.width = 0;
    };
  }, [sourceKey, isImage, imageRef, videoRef, canvasRef]);

  useLayoutEffect(() => {
    paintRef.current?.(frameTime.current);
  }, [regions, enabled]);

  useLayoutEffect(() => {
    if (!isImage && videoRef.current?.paused) paintRef.current?.(currentTimeMs);
  }, [currentTimeMs, isImage, videoRef]);

  return {
    ready: enabled && result.key === sourceKey && result.ready,
    error: enabled && result.key === sourceKey ? result.error : null,
  };
}
