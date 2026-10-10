import { useState } from "react";
import { AlertTriangle, CheckCircle2, Copy, Download, History, Loader2, RotateCcw, ThumbsDown, ThumbsUp } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { MAX_REASON_CHARS, type HistoryEntry, type Snapshot } from "@/lib/review/types";

export function MaskedText({ text, className = "" }: { text: string; className?: string }) {
  const parts = text.split(/(\*+)/);
  return (
    <pre className={`whitespace-pre-wrap break-words font-mono text-sm leading-7 text-foreground ${className}`}>
      {parts.map((p, i) =>
        p.startsWith("*") ? (
          <mark key={i} className="rounded-sm bg-primary px-1 text-primary-foreground" aria-label="redacted data">
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
  const [rejectOpen, setRejectOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [copied, setCopied] = useState(false);
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

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Attempt" value={snapshot.attempt} />
        <Stat label="Redacted items" value={masks} />
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

      <section className="relative">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-base font-bold text-foreground">Version {snapshot.attempt}</h3>
          <div className="flex flex-wrap gap-2">
            <Button variant="ghost" size="sm" onClick={() => setHistoryOpen(true)} disabled={busy}>
              <History aria-hidden /> History ({snapshot.history.length})
            </Button>
            <Button variant="ghost" size="sm" disabled={busy} onClick={async () => {
              await navigator.clipboard.writeText(snapshot.text);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            }}>
              <Copy aria-hidden /> {copied ? "Copied!" : "Copy"}
            </Button>
            <Button variant="ghost" size="sm" onClick={download} disabled={busy}>
              <Download aria-hidden /> Download .txt
            </Button>
          </div>
        </div>
        <div className="document-paper max-h-[34rem] overflow-auto rounded-lg border border-border bg-card p-6" aria-busy={busy}>
          <MaskedText text={snapshot.text} className={busy ? "opacity-40" : ""} />
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

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reject version {snapshot.attempt}</DialogTitle>
            <DialogDescription>Explain what should change: hide more, or keep visible something that was hidden.</DialogDescription>
          </DialogHeader>
          <Textarea
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={MAX_REASON_CHARS}
            rows={5}
            placeholder="E.g.: also hide the doctor's name and the diagnosis."
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
                <p className="text-sm font-bold text-foreground">Attempt {h.attempt}</p>
                <p className="mt-1 text-sm text-muted-foreground">“{h.reason}”</p>
                <div className="mt-3 max-h-60 overflow-auto rounded-md bg-muted p-3">
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
