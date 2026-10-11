import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Copy,
  Download,
  History,
  Loader2,
  Plus,
  RotateCcw,
  ShieldCheck,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Progress as ProgressBar } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  ApiError,
  MAX_REASON_CHARS,
  stageLabel,
  type HistoryEntry,
  type MediaRegion,
  type RegionBox,
  type Snapshot,
} from "@/lib/review/types";
import {
  censoredAudioUrl,
  getCurrent,
  mediaOutputUrl,
  trackRegion,
  updateRegions,
} from "@/lib/review/api";
import {
  MediaRegionsList,
  MediaViewer,
  VideoTimeline,
  updateRegionBoxAtTime,
} from "./media-review";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

interface TextPart {
  type: "text";
  text: string;
}

interface MaskedPart {
  type: "masked";
  text: string;
  originalWord?: string | undefined;
}

type Part = TextPart | MaskedPart;

function alignLine(maskLine: string, origLine?: string): Part[] {
  const tokens = maskLine.split(/(\*+)/);
  if (!origLine) {
    return tokens
      .filter(Boolean)
      .map((t) => (t.startsWith("*") ? { type: "masked", text: t } : { type: "text", text: t }));
  }

  const parts: Part[] = [];
  let origIdx = 0;

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];
    if (!token) continue;

    if (token.startsWith("*")) {
      const nextLit = tokens[i + 1] ?? "";
      let origWord = "";
      if (!nextLit) {
        origWord = origLine.slice(origIdx);
        origIdx = origLine.length;
      } else {
        const pos = origLine.indexOf(nextLit, origIdx);
        if (pos !== -1) {
          origWord = origLine.slice(origIdx, pos);
          origIdx = pos;
        } else {
          const trimmedLit = nextLit.trimStart();
          const firstChar = trimmedLit[0];
          const charPos = firstChar ? origLine.indexOf(firstChar, origIdx) : -1;
          if (charPos !== -1) {
            origWord = origLine.slice(origIdx, charPos);
            origIdx = charPos;
          } else {
            origWord = "";
          }
        }
      }
      const cleanWord = origWord.trim();
      parts.push({
        type: "masked",
        text: token,
        originalWord: cleanWord || undefined,
      });
    } else {
      origIdx += token.length;
      parts.push({ type: "text", text: token });
    }
  }

  return parts;
}

export function MaskedText({
  text,
  originalText,
  className = "",
}: {
  text: string;
  originalText?: string;
  className?: string;
}) {
  const maskLines = text.split("\n");
  const origLines = originalText ? originalText.split("\n") : [];

  return (
    <TooltipProvider delayDuration={150} skipDelayDuration={300}>
      <pre className={`whitespace-pre-wrap break-words font-mono text-sm leading-7 text-foreground ${className}`}>
        {maskLines.map((maskLine, lineIdx) => {
          const parts = alignLine(maskLine, origLines[lineIdx]);
          return (
            <span key={lineIdx}>
              {parts.map((part, partIdx) => {
                if (part.type !== "masked") {
                  return <span key={partIdx}>{part.text}</span>;
                }

                if (!part.originalWord) {
                  return (
                    <mark
                      key={partIdx}
                      className="masked-mark rounded-sm px-1 font-mono"
                      aria-label="redacted data"
                    >
                      {part.text}
                    </mark>
                  );
                }

                return (
                  <Tooltip key={partIdx}>
                    <TooltipTrigger asChild>
                      <mark
                        tabIndex={0}
                        className="masked-mark cursor-pointer rounded-sm px-1 font-mono transition-all duration-150 hover:opacity-90 hover:ring-2 hover:ring-primary/40 focus:outline-none focus:ring-2 focus:ring-primary"
                        aria-label={`redacted: ${part.originalWord}`}
                      >
                        {part.text}
                      </mark>
                    </TooltipTrigger>
                    <TooltipContent
                      side="top"
                      avoidCollisions
                      sideOffset={6}
                      className="z-50 select-none rounded-md border border-border/80 bg-popover px-2.5 py-1.5 text-xs text-popover-foreground shadow-lg backdrop-blur"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono font-semibold text-primary">
                          {part.originalWord}
                        </span>
                      </div>
                    </TooltipContent>
                  </Tooltip>
                );
              })}
              {lineIdx < maskLines.length - 1 ? "\n" : null}
            </span>
          );
        })}
      </pre>
    </TooltipProvider>
  );
}

function Stat({ label, value, tone }: { label: string; value: string | number; tone?: "warn" | undefined }) {
  return (
    <div className="rounded-lg border border-border bg-card px-4 py-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={`mt-1 text-lg font-bold ${tone === "warn" ? "text-destructive" : "text-foreground"}`}>{value}</p>
    </div>
  );
}

export function ReviewWorkspace({
  snapshot,
  busy,
  busyMessage,
  error,
  onRetry,
  onReject,
  onApprove,
  onNewDocument,
  onSnapshotChange,
}: {
  snapshot: Snapshot;
  busy: boolean;
  busyMessage: string;
  error: string | null;
  onRetry: (() => void) | null;
  onReject: (reason: string) => Promise<boolean>;
  onApprove: () => void;
  onNewDocument: () => void;
  onSnapshotChange?: (snapshot: Snapshot) => void;
}) {
  const [activeSnapshot, setActiveSnapshot] = useState<Snapshot>(snapshot);
  useEffect(() => {
    setActiveSnapshot(snapshot);
  }, [snapshot]);

  const isAudio = activeSnapshot.kind === "audio";
  const isImage = activeSnapshot.kind === "image";
  const isVideo = activeSnapshot.kind === "video";
  const isMedia = isImage || isVideo;
  const audioUrl = censoredAudioUrl(activeSnapshot);
  const mediaUrl = mediaOutputUrl(activeSnapshot);

  const [rejectOpen, setRejectOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [copied, setCopied] = useState(false);
  const [downloadingAudio, setDownloadingAudio] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);

  // Media download state
  const [downloadingMedia, setDownloadingMedia] = useState(false);
  const [mediaError, setMediaError] = useState<string | null>(null);

  // Media review state
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null);
  const [currentTimeMs, setCurrentTimeMs] = useState(0);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // Draft regions state for editing
  const [draftRegions, setDraftRegions] = useState<MediaRegion[]>(activeSnapshot.regions ?? []);
  const [removedHistory, setRemovedHistory] = useState<MediaRegion[]>([]);
  const [isDrawing, setIsDrawing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Tracking state
  const [trackingRegionId, setTrackingRegionId] = useState<string | null>(null);
  const [trackError, setTrackError] = useState<string | null>(null);

  // Sync draft when attempt or active snapshot changes from outside
  useEffect(() => {
    setDraftRegions(activeSnapshot.regions ?? []);
    setRemovedHistory([]);
    setSaveError(null);
  }, [activeSnapshot.attempt, activeSnapshot.regions]);

  const isDirty = useMemo(() => {
    if (!isMedia) return false;
    return JSON.stringify(draftRegions) !== JSON.stringify(activeSnapshot.regions);
  }, [isMedia, draftRegions, activeSnapshot.regions]);

  const validationErrors = useMemo(() => {
    const errors: Record<string, string> = {};
    if (!isVideo) return errors;
    const duration = activeSnapshot.media.duration_ms ?? 0;
    for (const r of draftRegions) {
      if (r.end_ms < r.start_ms) {
        errors[r.id] = "End time must be after or equal to start time.";
      } else if (r.start_ms < 0) {
        errors[r.id] = "Start time cannot be negative.";
      } else if (duration > 0 && r.end_ms > duration) {
        errors[r.id] = `End time cannot exceed video duration (${(duration / 1000).toFixed(1)}s).`;
      }
    }
    return errors;
  }, [isVideo, activeSnapshot.media.duration_ms, draftRegions]);

  const hasValidationErrors = Object.keys(validationErrors).length > 0;

  const handleUpdateRegionBox = (regionId: string, newBox: RegionBox) => {
    setDraftRegions((prev) =>
      prev.map((r) =>
        r.id === regionId ? updateRegionBoxAtTime(r, newBox, currentTimeMs, isImage) : r,
      ),
    );
  };

  const handleUpdateRegion = (id: string, updates: Partial<MediaRegion>) => {
    setDraftRegions((prev) => prev.map((r) => (r.id === id ? { ...r, ...updates } : r)));
  };

  const handleAddRegion = (newRegion: MediaRegion) => {
    setDraftRegions((prev) => [...prev, newRegion]);
    setSelectedRegionId(newRegion.id);
    setIsDrawing(false);
  };

  const handleRemoveRegion = (id: string) => {
    const target = draftRegions.find((r) => r.id === id);
    if (!target) return;
    setRemovedHistory((prev) => [...prev, target]);
    setDraftRegions((prev) => prev.filter((r) => r.id !== id));
    if (selectedRegionId === id) setSelectedRegionId(null);
  };

  const handleUndoRemove = () => {
    if (removedHistory.length === 0) return;
    const last = removedHistory[removedHistory.length - 1];
    setRemovedHistory((prev) => prev.slice(0, -1));
    if (!last) return;
    setDraftRegions((prev) => [...prev, last]);
    setSelectedRegionId(last.id);
  };

  const handleDiscard = () => {
    setDraftRegions(structuredClone(activeSnapshot.regions));
    setRemovedHistory([]);
    setSaveError(null);
    setIsDrawing(false);
    setSelectedRegionId(null);
  };

  const handleSave = async () => {
    if (hasValidationErrors) return;
    setIsSaving(true);
    setSaveError(null);
    try {
      const updated = await updateRegions(activeSnapshot.attempt, draftRegions);
      setActiveSnapshot(updated);
      setDraftRegions(updated.regions);
      setRemovedHistory([]);
      onSnapshotChange?.(updated);
    } catch (err: any) {
      const status = err?.status;
      if (status === 409) {
        try {
          const refreshed = await getCurrent();
          setActiveSnapshot(refreshed);
          setDraftRegions(refreshed.regions);
          setRemovedHistory([]);
          onSnapshotChange?.(refreshed);
        } catch {}
        setSaveError(err.message || "The version under review has changed. Refresh and try again.");
      } else if (status === 422) {
        setSaveError(err.message || "A hiding interval is not valid.");
      } else {
        setSaveError(err instanceof Error ? err.message : "Failed to save changes.");
      }
    } finally {
      setIsSaving(false);
    }
  };

  const handleTrackRegion = async (region: MediaRegion) => {
    setTrackingRegionId(region.id);
    setTrackError(null);
    try {
      const tracked = await trackRegion(activeSnapshot.attempt, currentTimeMs, region);
      setDraftRegions((prev) => prev.map((r) => (r.id === region.id ? tracked : r)));
    } catch (err) {
      setTrackError(err instanceof Error ? err.message : "Failed to track region.");
    } finally {
      setTrackingRegionId(null);
    }
  };

  const masks = (activeSnapshot.text.match(/\*+/g) ?? []).length;

  const submitReject = async () => {
    setRejectOpen(false);
    if (await onReject(reason.trim())) setReason("");
  };

  const download = () => {
    const url = URL.createObjectURL(new Blob([activeSnapshot.text], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `anonymized-document-v${activeSnapshot.attempt}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadAudio = async () => {
    const url = censoredAudioUrl(activeSnapshot);
    if (!url) {
      setAudioError("No audio available");
      return;
    }
    setDownloadingAudio(true);
    setAudioError(null);
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Download failed: ${res.status}`);
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = "censored-audio.m4a";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch (err) {
      setAudioError(err instanceof Error ? err.message : "Failed to download audio.");
    } finally {
      setDownloadingAudio(false);
    }
  };

  const downloadMedia = async () => {
    const url = mediaOutputUrl(activeSnapshot);
    if (!url) {
      setMediaError(isVideo ? "No video available" : "No image available");
      return;
    }
    setDownloadingMedia(true);
    setMediaError(null);
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(`Download failed: ${res.status}`);
      const blob = await res.blob();

      let filename: string;
      if (isVideo) {
        filename = "anonymized-video.mp4";
      } else {
        let ext = "png";
        if (activeSnapshot.media.filename && activeSnapshot.media.filename.includes(".")) {
          ext = activeSnapshot.media.filename.split(".").pop()?.toLowerCase() || "png";
        } else if (activeSnapshot.media.output_url) {
          const dataMatch = activeSnapshot.media.output_url.match(/^data:image\/([a-zA-Z0-9+]+)/);
          if (dataMatch?.[1]) {
            ext = dataMatch[1] === "jpeg" ? "jpg" : dataMatch[1];
          } else {
            const urlMatch = activeSnapshot.media.output_url.match(/\.([a-zA-Z0-9]+)(?:[?#]|$)/);
            if (urlMatch?.[1]) ext = urlMatch[1].toLowerCase();
          }
        }
        filename = `anonymized-image.${ext}`;
      }

      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch (err) {
      setMediaError(err instanceof Error ? err.message : "Failed to download media.");
    } finally {
      setDownloadingMedia(false);
    }
  };

  const steps: { title: string; note: string; state: "done" | "now" | "todo" }[] = [
    {
      title: isAudio
        ? "Audio received"
        : isImage
        ? "Image received"
        : isVideo
        ? "Video received"
        : "Document received",
      note: isAudio ? "Transcribed" : "Analyzed",
      state: "done",
    },
    {
      title: "Manual review",
      note: `Attempt ${activeSnapshot.attempt}`,
      state: activeSnapshot.approved ? "done" : "now",
    },
    {
      title: "Final approval",
      note: activeSnapshot.approved ? `Version ${activeSnapshot.attempt}` : "Waiting for your review",
      state: activeSnapshot.approved ? "done" : "todo",
    },
  ];

  const hasFailed = activeSnapshot.status === "failed";
  const isWorkingState = activeSnapshot.status === "processing" || activeSnapshot.status === "exporting";
  const errorMessage = activeSnapshot.error || error || "Analysis failed";

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[240px_minmax(0,1fr)_280px]">
      <aside aria-label="Progress" className="lg:sticky lg:top-24">
        <ol className="steps-list rounded-2xl border border-border bg-card p-5 lg:border-0 lg:bg-transparent lg:p-0">
          {steps.map((s) => (
            <li
              key={s.title}
              className={`grid grid-cols-[32px_1fr] gap-3.5 pb-6 last:pb-0 step-${s.state} ${s.state === "todo" ? "text-muted-foreground" : ""}`}
            >
              <span
                className={`step-dot grid h-8 w-8 place-items-center rounded-full border text-[13px] font-semibold ${
                  s.state === "done"
                    ? "border-ok text-ok"
                    : s.state === "now"
                      ? "brand-gradient glow-ring border-transparent text-white"
                      : "border-border bg-card"
                }`}
              >
                {s.state === "done" && <Check className="h-4 w-4" aria-hidden />}
              </span>
              <span>
                <b className={`block text-[15px] ${s.state === "todo" ? "text-muted-foreground" : "text-foreground"}`}>
                  {s.title}
                </b>
                <small className="text-[13px] text-muted-foreground">{s.note}</small>
              </span>
            </li>
          ))}
        </ol>
      </aside>

      <div className="flex min-w-0 flex-col gap-6">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Attempt" value={activeSnapshot.attempt} />
          {isMedia ? (
            <Stat label="Regions" value={draftRegions.length} />
          ) : isAudio ? (
            <Stat label="Replaced stretches" value={activeSnapshot.audio_ranges} />
          ) : (
            <Stat label="Masked words" value={masks} />
          )}
          <Stat
            label="Warnings"
            value={isMedia ? 0 : activeSnapshot.warnings}
            tone={!isMedia && activeSnapshot.warnings > 0 ? "warn" : undefined}
          />
          <Stat
            label="Issues"
            value={isMedia ? 0 : activeSnapshot.issues}
            tone={!isMedia && activeSnapshot.issues > 0 ? "warn" : undefined}
          />
        </div>

        {activeSnapshot.mode === "rules" && (
          <p className="rounded-lg border border-border bg-muted px-4 py-3 text-sm text-muted-foreground">
            Rules-only mode: feedback does not change the text.
          </p>
        )}

        {(hasFailed || error) && (
          <div
            role="alert"
            className="flex flex-wrap items-center gap-3 rounded-lg border border-destructive/40 bg-card px-4 py-3"
          >
            <AlertTriangle className="h-5 w-5 text-destructive" aria-hidden />
            <p className="min-w-0 flex-1 text-sm text-foreground">{errorMessage}</p>
            {onRetry && (
              <Button variant="outline" size="sm" onClick={onRetry} disabled={busy}>
                <RotateCcw aria-hidden /> Try again
              </Button>
            )}
          </div>
        )}

        {activeSnapshot.approved && (
          <div className="flex items-center gap-3 rounded-lg border border-primary/40 bg-accent px-4 py-3 text-sm font-medium text-foreground">
            <CheckCircle2 className="h-5 w-5 text-primary" aria-hidden /> Version {activeSnapshot.attempt} approved.
          </div>
        )}

        {/* Media center view: image or video */}
        {isMedia ? (
          <section className="relative space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-foreground">
                  {isImage ? "Image preview" : "Video preview"}
                </h3>
                {isDirty && (
                  <span className="rounded-full border border-warn/40 bg-warn/10 px-2.5 py-0.5 text-xs font-semibold text-warn">
                    Unsaved changes
                  </span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant={isDrawing ? "default" : "outline"}
                  size="sm"
                  onClick={() => setIsDrawing(!isDrawing)}
                >
                  <Plus className="h-4 w-4 mr-1" />
                  {isDrawing ? "Cancel drawing" : "Add region"}
                </Button>
                {isDirty && (
                  <>
                    <Button variant="ghost" size="sm" onClick={handleDiscard} disabled={isSaving}>
                      Discard
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleSave}
                      disabled={isSaving || hasValidationErrors}
                    >
                      {isSaving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}
                      Save changes
                    </Button>
                  </>
                )}
                <Button variant="ghost" size="sm" onClick={() => setHistoryOpen(true)} disabled={busy}>
                  <History aria-hidden /> History ({activeSnapshot.history.length})
                </Button>
                {activeSnapshot.approved && mediaUrl && !isDirty && (
                  <Button
                    size="sm"
                    onClick={downloadMedia}
                    disabled={busy || downloadingMedia}
                  >
                    {downloadingMedia ? (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    ) : (
                      <Download aria-hidden />
                    )}
                    {isVideo ? "Download video" : "Download image"}
                  </Button>
                )}
              </div>
            </div>

            {saveError && (
              <p role="alert" className="text-sm text-destructive">{saveError}</p>
            )}

            {trackError && (
              <p role="alert" className="text-sm text-destructive">{trackError}</p>
            )}

            {mediaError && (
              <p role="alert" className="text-sm text-destructive">{mediaError}</p>
            )}

            <div className="relative">
              <MediaViewer
                snapshot={activeSnapshot}
                currentTimeMs={currentTimeMs}
                onTimeUpdate={setCurrentTimeMs}
                selectedRegionId={selectedRegionId}
                onSelectRegion={setSelectedRegionId}
                videoRef={videoRef}
                regions={draftRegions}
                onUpdateRegionBox={handleUpdateRegionBox}
                onAddRegion={handleAddRegion}
                onRemoveRegion={handleRemoveRegion}
                isDrawing={isDrawing}
                onToggleDrawMode={() => setIsDrawing(!isDrawing)}
              />

              {/* Progress bar overlay during processing or exporting */}
              {isWorkingState && (
                <div
                  className="absolute inset-0 z-30 flex flex-col items-center justify-center rounded-2xl bg-background/80 p-6 backdrop-blur-sm"
                  role="status"
                >
                  <div className="w-full max-w-sm space-y-3 rounded-xl border border-border bg-card p-6 shadow-lg">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span className="font-semibold text-foreground">
                        {stageLabel(activeSnapshot.progress.stage)}
                      </span>
                      <span className="tabular-nums font-semibold text-foreground">
                        {activeSnapshot.progress.total > 0
                          ? `${Math.min(100, Math.round((activeSnapshot.progress.completed / activeSnapshot.progress.total) * 100))}%`
                          : ""}
                      </span>
                    </div>
                    <ProgressBar
                      value={
                        activeSnapshot.progress.total > 0
                          ? (activeSnapshot.progress.completed / activeSnapshot.progress.total) * 100
                          : undefined
                      }
                      aria-label="Progress"
                      className="h-2 w-full"
                    />
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>
                        {activeSnapshot.progress.completed} of {activeSnapshot.progress.total}
                      </span>
                      <span className="flex items-center gap-1.5">
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-brand" /> Working
                      </span>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {isVideo && (
              <VideoTimeline
                snapshot={activeSnapshot}
                currentTimeMs={currentTimeMs}
                onSeek={(ms: number) => {
                  setCurrentTimeMs(ms);
                  if (videoRef.current) {
                    videoRef.current.currentTime = ms / 1000;
                  }
                }}
                regions={draftRegions}
                onUpdateRegion={handleUpdateRegion}
              />
            )}
          </section>
        ) : (
          <>
            {isAudio && (
              <div className="rounded-lg border border-border bg-card p-6">
                <h3 className="text-base font-bold text-foreground">Censored audio</h3>
                <div className="mt-4">
                  {audioUrl ? (
                    <audio
                      key={activeSnapshot.attempt}
                      controls
                      preload="metadata"
                      src={audioUrl}
                      className="w-full"
                    />
                  ) : (
                    <p className="text-sm text-muted-foreground">No audio available</p>
                  )}
                </div>
                <p className="mt-2 text-xs text-muted-foreground">Each masked word was replaced by a sound.</p>
                {audioError && (
                  <p role="alert" className="mt-2 text-sm text-destructive">{audioError}</p>
                )}
              </div>
            )}

            <section className="relative">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h3 className="text-base font-bold text-foreground">
                  {isAudio ? "Masked transcript" : `Version ${activeSnapshot.attempt}`}
                </h3>
                <div className="flex flex-wrap gap-2">
                  <Button variant="ghost" size="sm" onClick={() => setHistoryOpen(true)} disabled={busy}>
                    <History aria-hidden /> History ({activeSnapshot.history.length})
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    disabled={busy}
                    onClick={async () => {
                      await navigator.clipboard.writeText(activeSnapshot.text);
                      setCopied(true);
                      setTimeout(() => setCopied(false), 2000);
                    }}
                  >
                    <Copy aria-hidden /> {copied ? "Copied!" : "Copy"}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={download} disabled={busy}>
                    <Download aria-hidden /> Download .txt
                  </Button>
                  {isAudio && (
                    <Button variant="ghost" size="sm" onClick={downloadAudio} disabled={busy || downloadingAudio}>
                      {downloadingAudio ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : <Download aria-hidden />} Download audio
                    </Button>
                  )}
                </div>
              </div>
              <div key={activeSnapshot.attempt} className="document-paper stage-frame stage-scan rounded-2xl border border-border bg-card" aria-busy={busy}>
                <div className="max-h-[34rem] overflow-y-auto p-6 clean-scrollbar" tabIndex={0} aria-label="Anonymized text">
                  <MaskedText
                    text={activeSnapshot.text}
                    originalText={activeSnapshot.original_text}
                    className={`stage-pv ${busy ? "opacity-40" : ""}`}
                  />
                </div>
              </div>
              {busy && (
                <div className="absolute inset-0 top-10 grid place-items-center rounded-lg bg-background/60" role="status">
                  <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-5 py-3 text-sm font-medium text-foreground">
                    <Loader2 className="h-5 w-5 animate-spin text-primary" aria-hidden /> {busyMessage}
                  </div>
                </div>
              )}
            </section>
          </>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button variant="outline" onClick={onNewDocument} disabled={busy}>
            New document
          </Button>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              onClick={() => setRejectOpen(true)}
              disabled={busy || isWorkingState || isDirty || (!isMedia && activeSnapshot.approved)}
              title={isDirty ? "Save or discard your changes first" : undefined}
            >
              <ThumbsDown aria-hidden /> Reject
            </Button>
            <Button
              onClick={onApprove}
              disabled={busy || activeSnapshot.approved || isWorkingState || isDirty}
              title={isDirty ? "Save or discard your changes first" : undefined}
              className="h-10 px-5"
            >
              <ThumbsUp aria-hidden /> Approve version
            </Button>
          </div>
        </div>
      </div>

      {/* Right panel */}
      <aside aria-label="Review details" className="rounded-2xl border border-border bg-card p-5">
        <div className="mb-4 flex items-center justify-between border-b border-border pb-3.5 font-semibold">
          <span className="flex items-center gap-2.5">
            <History className="h-[18px] w-[18px]" aria-hidden /> Review
          </span>
          <span
            className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
              activeSnapshot.approved ? "border-ok/40 bg-ok/10 text-ok" : "border-warn/40 bg-warn/10 text-warn"
            }`}
          >
            {activeSnapshot.approved ? "Approved" : "In review"}
          </span>
        </div>

        {isMedia ? (
          <div>
            <div className="relative mb-4 overflow-hidden rounded-xl border border-border bg-background py-3.5 pl-5 pr-4 text-sm">
              <span className="brand-gradient absolute inset-y-0 left-0 w-1" aria-hidden />
              <b>Sensitive regions</b>
              <small className="mt-1 block text-[13px] text-muted-foreground">
                {draftRegions.length} detected · {isImage ? "Photo" : "Video"}
              </small>
            </div>

            {removedHistory.length > 0 && (
              <div className="mb-3 flex items-center justify-between rounded-lg border border-border bg-muted/60 px-3 py-2 text-xs">
                <span>
                  {removedHistory.length} region{removedHistory.length > 1 ? "s" : ""} removed
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleUndoRemove}
                  className="h-7 text-xs"
                >
                  <RotateCcw className="h-3 w-3 mr-1" /> Undo
                </Button>
              </div>
            )}

            <MediaRegionsList
              regions={draftRegions}
              selectedRegionId={selectedRegionId}
              onSelectRegion={setSelectedRegionId}
              onUpdateRegion={handleUpdateRegion}
              onRemoveRegion={handleRemoveRegion}
              onTrackRegion={isVideo ? handleTrackRegion : undefined}
              trackingRegionId={trackingRegionId}
              isAudioOrImage={isImage}
              durationMs={activeSnapshot.media.duration_ms ?? 0}
              validationErrors={validationErrors}
            />
          </div>
        ) : (
          <>
            <div className="relative overflow-hidden rounded-xl border border-border bg-background py-3.5 pl-5 pr-4 text-sm">
              <span className="brand-gradient absolute inset-y-0 left-0 w-1" aria-hidden />
              <b>Current version</b>
              <small className="mt-1 block text-[13px] text-muted-foreground">
                {isAudio ? "Audio censored" : "Text anonymized"} · {activeSnapshot.history.length} rejected
              </small>
            </div>
            <div className="mt-3.5 divide-y divide-border text-sm text-muted-foreground">
              <div className="flex justify-between py-3">
                Type <b className="font-semibold text-foreground">{isAudio ? "Audio" : "Document"}</b>
              </div>
              <div className="flex justify-between py-3">
                Mode <b className="font-semibold text-foreground">{activeSnapshot.mode === "rules" ? "Rules only" : "AI + rules"}</b>
              </div>
            </div>
          </>
        )}

        <div className="mt-4 border-t border-border pt-4 text-[13px] text-muted-foreground">
          <b className="mb-1.5 flex items-center gap-2 text-sm text-foreground">
            <ShieldCheck className="h-4 w-4 text-ok" aria-hidden /> Temporary session
          </b>
          Nothing is stored after you close the review. Hover a * to see the word it hides.
        </div>
      </aside>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject version {activeSnapshot.attempt}</DialogTitle>
            <DialogDescription>
              {isAudio
                ? "The audio is not uploaded again; the transcript is analysed again with your feedback."
                : isMedia
                ? "The file is analysed again with your feedback and the current regions are replaced."
                : "Explain what should change: hide more, or keep visible something that was hidden."}
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={MAX_REASON_CHARS}
            rows={5}
            placeholder="E.g.: also hide the clinic name - or: do not hide medical information."
            aria-label="Feedback"
          />
          <p className="text-right text-xs text-muted-foreground">{reason.length} / {MAX_REASON_CHARS}</p>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRejectOpen(false)}>Cancel</Button>
            <Button onClick={submitReject} disabled={!reason.trim()}>Generate new version</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Sheet open={historyOpen} onOpenChange={setHistoryOpen}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>Rejected versions</SheetTitle>
            <SheetDescription>Newest first.</SheetDescription>
          </SheetHeader>
          <div className="mt-6 flex flex-col gap-4 px-4 pb-6">
            {activeSnapshot.history.length === 0 && <p className="text-sm text-muted-foreground">No rejected versions yet.</p>}
            {[...activeSnapshot.history].reverse().map((h: HistoryEntry) => (
              <article key={h.attempt} className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-bold text-foreground">Attempt {h.attempt}</p>
                  {isAudio && <span className="text-xs font-medium text-muted-foreground">Transcript</span>}
                  {isMedia && (
                    <span className="text-xs font-semibold text-muted-foreground">
                      {h.regions !== null ? `${h.regions} regions` : "0 regions"}
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">“{h.reason}”</p>
                {!isMedia && (
                  <div className="mt-3 max-h-60 overflow-auto rounded-md bg-muted p-3 clean-scrollbar">
                    <MaskedText text={h.text} originalText={activeSnapshot.original_text} className="text-xs leading-6" />
                  </div>
                )}
              </article>
            ))}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
