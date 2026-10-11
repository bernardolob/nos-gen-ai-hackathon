import { useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  FileText,
  Image as ImageIcon,
  Loader2,
  LockKeyhole,
  Music,
  Upload,
  Video,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Progress as ProgressBar } from "@/components/ui/progress";
import {
  ACCEPT_AUDIO,
  ACCEPT_DOCUMENTS,
  ACCEPT_MEDIA,
  isAudioFile,
  isMediaFile,
  isVideoFile,
} from "@/lib/review/api";
import type { Progress } from "@/lib/review/types";

const FORMATS = [
  "PDF",
  "TXT",
  "MD",
  "MP3",
  "M4A",
  "WAV",
  "JPG",
  "PNG",
  "WEBP",
  "MP4",
  "MOV",
  "WEBM",
];

const formatSize = (bytes: number) => {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(bytes / 1024).toFixed(1)} KB`;
};

/* ---------------- UploadStep ---------------- */

export function UploadStep({
  file,
  onFile,
  onAnalyze,
  loading,
  status,
  progress,
  error,
  errorTitle,
  onRetry,
  audioEnabled = false,
}: {
  file: File | null;
  onFile: (f: File | null) => void;
  onAnalyze: () => void;
  loading: boolean;
  status: string;
  progress?: Progress | null;
  error: string | null;
  errorTitle?: string;
  onRetry: () => void;
  audioEnabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [prevFile, setPrevFile] = useState<File | null>(file);

  if (file !== prevFile) {
    setPrevFile(file);
    setConfirmed(false);
  }

  const accept = (f: File | undefined) => {
    if (f) {
      onFile(f);
    }
  };

  const isAudio = Boolean(file && isAudioFile(file));
  const isMedia = Boolean(file && isMediaFile(file));
  const isVideo = Boolean(file && isVideoFile(file));
  const isImage = Boolean(file && isMedia && !isVideo);

  const needsConsent = isAudio || isMedia;
  const canAnalyze = Boolean(file && (!isAudio || audioEnabled) && (!needsConsent || confirmed));

  if (loading) {
    const hasTotal = Boolean(progress && progress.total > 0);
    const pct =
      hasTotal && progress
        ? Math.min(100, Math.max(0, Math.round((progress.completed / progress.total) * 100)))
        : null;
    const stageLabel = progress?.stage?.trim() || status;

    return (
      <div className="flex flex-col items-center gap-4 rounded-[20px] border border-border bg-card p-12 text-center">
        {hasTotal && pct !== null ? (
          <div className="w-full max-w-sm space-y-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span className="font-medium text-foreground" role="status">
                {stageLabel}
              </span>
              <span className="tabular-nums font-semibold text-foreground">{pct}%</span>
            </div>
            <ProgressBar value={pct} aria-label="Analysis progress" className="h-2 w-full" />
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>
                {progress?.completed} of {progress?.total} completed
              </span>
              <span>{isVideo ? "Analysis may take a while" : "Processing"}</span>
            </div>
          </div>
        ) : (
          <>
            <Loader2 className="h-10 w-10 animate-spin text-brand" aria-hidden />
            <p className="text-lg font-medium text-foreground" role="status">
              {stageLabel}
            </p>
            <p className="text-sm text-muted-foreground">
              {isVideo ? "Video analysis can take a while." : "This may take a few seconds."}
            </p>
          </>
        )}
      </div>
    );
  }

  if (error) {
    const title =
      errorTitle ??
      (file
        ? isMedia
          ? isVideo
            ? "The video could not be analyzed"
            : "The image could not be analyzed"
          : "The document could not be analyzed"
        : "Could not load the current review");
    return (
      <div className="flex flex-col items-center gap-4 rounded-[20px] border border-destructive/40 bg-card p-12 text-center">
        <AlertTriangle className="h-10 w-10 text-destructive" aria-hidden />
        <p className="text-lg font-medium text-foreground">{title}</p>
        <p className="text-sm text-muted-foreground">{error}</p>
        <Button onClick={onRetry}>Try again</Button>
      </div>
    );
  }

  return (
    <section className="min-w-0">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          accept(e.dataTransfer.files?.[0]);
        }}
        className={`drop-card flex flex-col items-center gap-1.5 rounded-[20px] px-6 pb-9 pt-12 text-center transition-shadow ${dragOver ? "is-over" : ""}`}
      >
        <div className="mb-2.5 grid h-[52px] w-[52px] place-items-center rounded-[14px] bg-[var(--glow)] text-brand">
          {isAudio ? (
            <Music className="h-6 w-6" aria-hidden />
          ) : isVideo ? (
            <Video className="h-6 w-6" aria-hidden />
          ) : isImage ? (
            <ImageIcon className="h-6 w-6" aria-hidden />
          ) : file ? (
            <FileText className="h-6 w-6" aria-hidden />
          ) : (
            <Upload className="h-6 w-6" aria-hidden />
          )}
        </div>
        {file ? (
          <div className="max-w-full">
            <p className="break-all text-xl font-semibold tracking-tight text-foreground">{file.name}</p>
            <p className="mt-1 text-sm text-muted-foreground">{formatSize(file.size)} · Ready to analyze</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {isVideo
                ? "Video up to 100 MB / 60 s / 1080p"
                : isImage
                ? "Image up to 20 MB"
                : isAudio
                ? "Audio up to 25 MB"
                : "Document up to 10 MB"}
            </p>
          </div>
        ) : (
          <div>
            <p className="text-xl font-semibold tracking-tight text-foreground">Drag and drop your file here</p>
            <p className="mt-1 text-sm text-muted-foreground">
              PDF, text, Markdown, audio, image (jpg, png, webp) or video (mp4, mov, webm)
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              10 MB documents · 25 MB audio · 20 MB images · 100 MB / 60 s / 1080p videos
            </p>
          </div>
        )}
        <input
          ref={inputRef}
          type="file"
          accept={`${ACCEPT_DOCUMENTS},${ACCEPT_AUDIO},${ACCEPT_MEDIA}`}
          className="sr-only"
          onChange={(e) => accept(e.target.files?.[0])}
        />
        <Button variant="outline" className="mt-4 bg-background" onClick={() => inputRef.current?.click()}>
          <Upload aria-hidden />
          {file ? "Choose another file" : "Choose file"}
        </Button>
        <span className="mt-5 flex items-center gap-2 text-[13px] text-muted-foreground">
          <LockKeyhole className="h-3.5 w-3.5 text-ok" aria-hidden /> Personal and sensitive data · GDPR
        </span>
      </div>

      <div className="marquee mt-8" aria-label="Accepted formats">
        <div className="marquee-track">
          {[...FORMATS, ...FORMATS].map((name, i) => (
            <span
              key={i}
              aria-hidden={i >= FORMATS.length ? true : undefined}
              className="rounded-full border border-border px-3 py-1 text-xs font-medium text-muted-foreground"
            >
              {name}
            </span>
          ))}
        </div>
      </div>

      {isAudio && (
        <div className="mt-6 space-y-3">
          <Alert className="border-border bg-card">
            <AlertTriangle className="h-4 w-4 text-warn" />
            <AlertDescription className="text-xs sm:text-sm text-foreground">
              The original audio, still containing the sensitive data, is sent to a third-party service (ElevenLabs) to be transcribed before it is censored. Only upload audio that is fictional or that you are allowed to process.
            </AlertDescription>
          </Alert>
          <div className="flex items-center space-x-2">
            <Checkbox
              id="audio-privacy-consent"
              checked={confirmed}
              onCheckedChange={(checked) => setConfirmed(checked === true)}
            />
            <Label
              htmlFor="audio-privacy-consent"
              className="cursor-pointer text-sm font-medium leading-none text-foreground peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              I understand
            </Label>
          </div>
        </div>
      )}

      {isMedia && (
        <div className="mt-6 space-y-3">
          <Alert className="border-border bg-card">
            <AlertTriangle className="h-4 w-4 text-warn" />
            <AlertDescription className="text-xs sm:text-sm text-foreground">
              Sampled frames are sent to a third-party AI model (Gemini) to identify sensitive regions before they are censored. Only upload photos or videos that you are allowed to process.
            </AlertDescription>
          </Alert>
          <div className="flex items-center space-x-2">
            <Checkbox
              id="media-privacy-consent"
              checked={confirmed}
              onCheckedChange={(checked) => setConfirmed(checked === true)}
            />
            <Label
              htmlFor="media-privacy-consent"
              className="cursor-pointer text-sm font-medium leading-none text-foreground peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              I understand
            </Label>
          </div>
        </div>
      )}

      <div className="mt-6 flex flex-wrap items-center justify-end gap-3">
        {isAudio && !audioEnabled && (
          <span className="text-sm font-medium text-destructive">Audio censoring is not available on this server.</span>
        )}
        <Button onClick={onAnalyze} disabled={!canAnalyze} className="btn-shine h-11 px-6">
          Analyze document <ArrowRight aria-hidden />
        </Button>
      </div>
    </section>
  );
}
