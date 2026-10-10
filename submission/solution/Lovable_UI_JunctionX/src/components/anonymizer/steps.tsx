import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  FileText,
  Loader2,
  LockKeyhole,
  Music,
  Plus,
  Upload,
} from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { ACCEPT_AUDIO, ACCEPT_DOCUMENTS, isAudioFile } from "@/lib/review/api";

/* ---------------- UploadStep ---------------- */

export function UploadStep({
  file,
  onFile,
  onAnalyze,
  loading,
  status,
  error,
  onRetry,
  audioEnabled = false,
}: {
  file: File | null;
  onFile: (f: File | null) => void;
  onAnalyze: () => void;
  loading: boolean;
  status: string;
  error: string | null;
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

  useEffect(() => {
    setConfirmed(false);
  }, [file]);

  const accept = (f: File | undefined) => {
    if (f) {
      setConfirmed(false);
      onFile(f);
    }
  };

  const isAudio = Boolean(file && isAudioFile(file));
  const canAnalyze = Boolean(file && (!isAudio || (audioEnabled && confirmed)));

  const activeStatus =
    isAudio && status === "Analyzing the document... (about 8 s)"
      ? "Transcribing and censoring the audio... this can take several seconds."
      : status ||
        (isAudio
          ? "Transcribing and censoring the audio... this can take several seconds."
          : "Analyzing the document... (about 8 s)");

  if (loading) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-lg border border-border bg-card p-16 text-center">
        <Loader2 className="h-10 w-10 animate-spin text-primary" aria-hidden />
        <p className="text-lg font-medium text-foreground" role="status">
          {activeStatus}
        </p>
        <p className="text-sm text-muted-foreground">This may take a few seconds.</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-lg border border-destructive/40 bg-card p-16 text-center">
        <AlertTriangle className="h-10 w-10 text-destructive" aria-hidden />
        <p className="text-lg font-medium text-foreground">The document could not be analyzed</p>
        <p className="text-sm text-muted-foreground">{error}</p>
        <Button
          variant="ghost"
          onClick={onRetry}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus-visible:outline-2 focus-visible:outline-ring"
        >
          Try again
        </Button>
      </div>
    );
  }

  return (
    <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_280px] lg:gap-12">
      <section className="min-w-0">
        <div className="mb-5 flex items-center justify-between gap-3">
          <h3 className="text-base font-bold text-foreground">Upload document</h3>
          <span className="font-mono text-xs text-muted-foreground">PDF / TXT / MD</span>
        </div>
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
          className={`flex min-h-[300px] flex-col items-center justify-center gap-5 rounded-lg border border-dashed px-5 py-10 text-center transition-colors ${dragOver ? "border-primary bg-accent" : "border-input bg-card"}`}
        >
          <div className="relative grid h-16 w-16 place-items-center rounded-lg border border-border bg-background text-primary">
            {isAudio ? (
              <Music className="h-7 w-7" strokeWidth={1.5} aria-hidden />
            ) : (
              <FileText className="h-7 w-7" strokeWidth={1.5} aria-hidden />
            )}
            <span className="absolute -bottom-2 -right-2 grid h-6 w-6 place-items-center rounded-full border-2 border-card bg-primary text-primary-foreground">
              <Plus className="h-3 w-3" aria-hidden />
            </span>
          </div>
          {file ? (
            <div className="max-w-full">
              <p className="break-all text-base font-semibold text-foreground">{file.name}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {(file.size / 1024).toFixed(1)} KB · Ready to analyze
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                10 MB documents, 25 MB audio
              </p>
            </div>
          ) : (
            <div>
              <p className="text-base font-semibold text-foreground">
                Drag and drop your document here
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                PDF, text, Markdown or audio (mp3, m4a, wav)
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                10 MB documents, 25 MB audio
              </p>
            </div>
          )}
          <input
            ref={inputRef}
            type="file"
            accept={`${ACCEPT_DOCUMENTS},${ACCEPT_AUDIO}`}
            className="sr-only"
            onChange={(e) => accept(e.target.files?.[0])}
          />
          <Button variant="outline" onClick={() => inputRef.current?.click()}>
            <Upload aria-hidden />
            {file ? "Choose another file" : "Choose file"}
          </Button>
        </div>

        {isAudio && (
          <div className="mt-4 space-y-3">
            <Alert className="border-border bg-card">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
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

        <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
          <span className="flex items-center gap-2 text-xs text-muted-foreground">
            <LockKeyhole className="h-3.5 w-3.5" aria-hidden /> Personal and sensitive data · GDPR
          </span>
          <div className="flex flex-wrap items-center gap-3">
            {isAudio && !audioEnabled && (
              <span className="text-sm font-medium text-destructive">
                Audio censoring is not available on this server.
              </span>
            )}
            <Button onClick={onAnalyze} disabled={!canAnalyze} className="h-11 px-5">
              Analyze document <ArrowRight aria-hidden />
            </Button>
          </div>
        </div>
      </section>
      <aside className="min-w-0 border-t border-border pt-6 lg:border-t-0 lg:pt-0">
        <div className="mb-5 flex items-center gap-2 text-xs font-semibold text-muted-foreground">
          <FileText className="h-4 w-4" aria-hidden /> Demo document
        </div>
        <div className="document-paper rounded-md border border-border bg-card p-6">
          <div className="mb-5 flex items-center justify-between border-b border-border pb-4">
            <span className="text-xs font-bold text-foreground">CLINICAL REPORT</span>
            <span className="font-mono text-[10px] text-muted-foreground">01</span>
          </div>
          <div className="space-y-4 text-xs leading-6 text-muted-foreground">
            <p>
              Patient:{" "}
              <span className="rounded-sm bg-accent px-1 py-0.5 font-medium text-primary">
                Maria Silva
              </span>
              <br />
              Date of birth:{" "}
              <span className="rounded-sm bg-accent px-1 py-0.5 font-medium text-primary">
                14/03/1985
              </span>
            </p>
            <p>
              The patient was seen at the clinic. Reports a history of{" "}
              <span className="rounded-sm bg-destructive/10 px-1 py-0.5 text-destructive">
                hypertension
              </span>
              .
            </p>
            <div aria-hidden className="space-y-2">
              <div className="h-1.5 w-full rounded-sm bg-muted" />
              <div className="h-1.5 w-full rounded-sm bg-muted" />
              <div className="h-1.5 w-2/3 rounded-sm bg-muted" />
            </div>
          </div>
          <div className="mt-7 flex items-center gap-2 border-t border-border pt-4 text-[10px] text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" /> Dummy data
          </div>
        </div>
      </aside>
    </div>
  );
}
