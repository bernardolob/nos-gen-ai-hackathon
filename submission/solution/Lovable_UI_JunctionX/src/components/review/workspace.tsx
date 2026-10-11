import { useState } from "react";
import { AlertTriangle, Check, CheckCircle2, Copy, Download, History, Loader2, RotateCcw, ShieldCheck, ThumbsDown, ThumbsUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { MAX_REASON_CHARS, type HistoryEntry, type Snapshot } from "@/lib/review/types";
import { censoredAudioUrl } from "@/lib/review/api";

export function MaskedText({ text, className = "" }: { text: string; className?: string }) {
  const parts = text.split(/(\*+)/);
  return (
    <pre className={`whitespace-pre-wrap break-words font-mono text-sm leading-7 text-foreground ${className}`}>
      {parts.map((p, i) =>
        p.startsWith("*") ? (
          <mark key={i} className="masked-mark rounded-sm px-1 font-mono" aria-label="redacted data">
            {p}
          </mark>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </pre>
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
}: {
  snapshot: Snapshot;
  busy: boolean;
  busyMessage: string;
  error: string | null;
  onRetry: (() => void) | null;
  onReject: (reason: string) => Promise<boolean>;
  onApprove: () => void;
  onNewDocument: () => void;
}) {
  const isAudio = snapshot.kind === "audio";
  const audioUrl = censoredAudioUrl(snapshot);

  const [rejectOpen, setRejectOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [copied, setCopied] = useState(false);
  const [downloadingAudio, setDownloadingAudio] = useState(false);
  const [audioError, setAudioError] = useState<string | null>(null);

  const masks = (snapshot.text.match(/\*+/g) ?? []).length;

  const submitReject = async () => {
    setRejectOpen(false);
    if (await onReject(reason.trim())) setReason("");
  };

  const download = () => {
    const url = URL.createObjectURL(new Blob([snapshot.text], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `anonymized-document-v${snapshot.attempt}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadAudio = async () => {
    const url = censoredAudioUrl(snapshot);
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

  const steps: { title: string; note: string; state: "done" | "now" | "todo" }[] = [
    { title: isAudio ? "Audio received" : "Document received", note: isAudio ? "Transcribed" : "Analyzed", state: "done" },
    {
      title: "Manual review",
      note: `Attempt ${snapshot.attempt}`,
      state: snapshot.approved ? "done" : "now",
    },
    {
      title: "Final approval",
      note: snapshot.approved ? `Version ${snapshot.attempt}` : "Waiting for your review",
      state: snapshot.approved ? "done" : "todo",
    },
  ];

  return (
    <div className="grid items-start gap-6 lg:grid-cols-[240px_minmax(0,1fr)_260px]">
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
        <Stat label="Attempt" value={snapshot.attempt} />
        {isAudio ? (
          <Stat label="Replaced stretches" value={snapshot.audio_ranges} />
        ) : (
          <Stat label="Masked words" value={masks} />
        )}
        <Stat label="Warnings" value={snapshot.warnings} tone={snapshot.warnings > 0 ? "warn" : undefined} />
        <Stat label="Issues" value={snapshot.issues} tone={snapshot.issues > 0 ? "warn" : undefined} />
      </div>

      {snapshot.mode === "rules" && (
        <p className="rounded-lg border border-border bg-muted px-4 py-3 text-sm text-muted-foreground">
          Rules-only mode: feedback does not change the text.
        </p>
      )}

      {error && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-destructive/40 bg-card px-4 py-3">
          <AlertTriangle className="h-5 w-5 text-destructive" aria-hidden />
          <p className="min-w-0 flex-1 text-sm text-foreground">{error}</p>
          {onRetry && (
            <Button variant="outline" size="sm" onClick={onRetry} disabled={busy}>
              <RotateCcw aria-hidden /> Try again
            </Button>
          )}
        </div>
      )}

      {snapshot.approved && (
        <div className="flex items-center gap-3 rounded-lg border border-primary/40 bg-accent px-4 py-3 text-sm font-medium text-foreground">
          <CheckCircle2 className="h-5 w-5 text-primary" aria-hidden /> Version {snapshot.attempt} approved.
        </div>
      )}

      {isAudio && (
        <div className="rounded-lg border border-border bg-card p-6">
          <h3 className="text-base font-bold text-foreground">Censored audio</h3>
          <div className="mt-4">
            {audioUrl ? (
              <audio
                key={snapshot.attempt}
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
            {isAudio ? "Masked transcript" : `Version ${snapshot.attempt}`}
          </h3>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" onClick={() => setHistoryOpen(true)} disabled={busy}>
              <History aria-hidden /> History ({snapshot.history.length})
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={busy}
              onClick={async () => {
                await navigator.clipboard.writeText(snapshot.text);
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
        {/* The frame clips the scan effect; the inner box is the one that scrolls. */}
        <div key={snapshot.attempt} className="document-paper stage-frame stage-scan rounded-2xl border border-border bg-card" aria-busy={busy}>
          <div className="max-h-[34rem] overflow-y-auto p-6 clean-scrollbar" tabIndex={0} aria-label="Anonymized text">
            <MaskedText text={snapshot.text} className={`stage-pv ${busy ? "opacity-40" : ""}`} />
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

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="outline" onClick={onNewDocument} disabled={busy}>New document</Button>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => setRejectOpen(true)} disabled={busy || snapshot.approved}>
            <ThumbsDown aria-hidden /> Reject
          </Button>
          <Button onClick={onApprove} disabled={busy || snapshot.approved} className="h-10 px-5">
            <ThumbsUp aria-hidden /> Approve version
          </Button>
        </div>
      </div>
      </div>

      <aside aria-label="Review details" className="rounded-2xl border border-border bg-card p-5">
        <div className="mb-4 flex items-center justify-between border-b border-border pb-3.5 font-semibold">
          <span className="flex items-center gap-2.5">
            <History className="h-[18px] w-[18px]" aria-hidden /> Review
          </span>
          <span
            className={`rounded-full border px-2.5 py-1 text-xs font-medium ${
              snapshot.approved ? "border-ok/40 bg-ok/10 text-ok" : "border-warn/40 bg-warn/10 text-warn"
            }`}
          >
            {snapshot.approved ? "Approved" : "In review"}
          </span>
        </div>
        <div className="relative overflow-hidden rounded-xl border border-border bg-background py-3.5 pl-5 pr-4 text-sm">
          <span className="brand-gradient absolute inset-y-0 left-0 w-1" aria-hidden />
          <b>Current version</b>
          <small className="mt-1 block text-[13px] text-muted-foreground">
            {isAudio ? "Audio censored" : "Text anonymized"} · {snapshot.history.length} rejected
          </small>
        </div>
        <div className="mt-3.5 divide-y divide-border text-sm text-muted-foreground">
          <div className="flex justify-between py-3">
            Type <b className="font-semibold text-foreground">{isAudio ? "Audio" : "Document"}</b>
          </div>
          <div className="flex justify-between py-3">
            Mode <b className="font-semibold text-foreground">{snapshot.mode === "rules" ? "Rules only" : "AI + rules"}</b>
          </div>
        </div>
        <div className="mt-1.5 border-t border-border pt-4 text-[13px] text-muted-foreground">
          <b className="mb-1.5 flex items-center gap-2 text-sm text-foreground">
            <ShieldCheck className="h-4 w-4 text-ok" aria-hidden /> Temporary session
          </b>
          Nothing is stored after you close the review. The original is never shown here.
        </div>
      </aside>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject version {snapshot.attempt}</DialogTitle>
            <DialogDescription>
              {isAudio
                ? "The audio is not uploaded again; the transcript is analysed again with your feedback."
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
            {snapshot.history.length === 0 && <p className="text-sm text-muted-foreground">No rejected versions yet.</p>}
            {[...snapshot.history].reverse().map((h: HistoryEntry) => (
              <article key={h.attempt} className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-bold text-foreground">Attempt {h.attempt}</p>
                  {isAudio && <span className="text-xs font-medium text-muted-foreground">Transcript</span>}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">“{h.reason}”</p>
                <div className="mt-3 max-h-60 overflow-auto rounded-md bg-muted p-3 clean-scrollbar">
                  <MaskedText text={h.text} className="text-xs leading-6" />
                </div>
              </article>
            ))}
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
