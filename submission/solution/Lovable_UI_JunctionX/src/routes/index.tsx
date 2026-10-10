import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Loader2, LockKeyhole, Moon, ShieldCheck, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { UploadStep } from "@/components/anonymizer/steps";
import { ReviewWorkspace } from "@/components/review/workspace";
import { approveVersion, getCurrent, isAudioFile, isMockMode, rejectVersion, uploadFile } from "@/lib/review/api";
import { ApiError, type Snapshot } from "@/lib/review/types";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Document Anonymizer" },
      {
        name: "description",
        content: "Upload a document, review the anonymized version, reject with feedback or approve (GDPR).",
      },
      { property: "og:title", content: "Document Anonymizer" },
      { property: "og:description", content: "Review of anonymized documents with personal and sensitive data (GDPR)." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: Index,
});

const message = (e: unknown) => (e instanceof Error ? e.message : "Something unexpected went wrong.");

function Index() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [initialising, setInitialising] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [wantsNew, setWantsNew] = useState(false);
  const [busy, setBusy] = useState(false);
  const [busyMessage, setBusyMessage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState<(() => void) | null>(null);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  const load = async () => {
    setInitialising(true);
    setError(null);
    try {
      setSnapshot(await getCurrent());
    } catch (e) {
      setError(message(e));
    } finally {
      setInitialising(false);
    }
  };
  useEffect(() => {
    void load();
  }, []);

  const upload = async () => {
    if (!file || uploading) return;
    setUploading(true);
    setError(null);
    try {
      setSnapshot(await uploadFile(file));
      setFile(null);
      setWantsNew(false);
    } catch (e) {
      setError(message(e));
    } finally {
      setUploading(false);
    }
  };

  const runAction = async (label: string, fn: () => Promise<Snapshot>, again: () => void): Promise<boolean> => {
    setBusy(true);
    setBusyMessage(label);
    setError(null);
    setRetry(null);
    try {
      setSnapshot(await fn());
      return true;
    } catch (e) {
      setError(message(e));
      // 502: the current version is unchanged, allow retrying the same action.
      if (e instanceof ApiError && (e.status === 502 || e.status === 0)) setRetry(() => again);
      // 409: the version moved on — refresh the snapshot.
      if (e instanceof ApiError && e.status === 409) {
        try {
          setSnapshot(await getCurrent());
        } catch {
          /* keep current snapshot */
        }
      }
      return false;
    } finally {
      setBusy(false);
    }
  };

  const reject = (reason: string): Promise<boolean> => {
    if (!snapshot) return Promise.resolve(false);
    const { attempt, text } = snapshot;
    const go = () => runAction("Generating a new version... (about 8 s)", () => rejectVersion(attempt, text, reason), () => void go());
    return go();
  };

  const approve = () => {
    const go = () => void runAction("Approving...", approveVersion, go);
    go();
  };

  const showUpload = !snapshot?.has_document || wantsNew;

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="border-b border-border bg-card">
        <div className="mx-auto grid w-full max-w-6xl grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-5 py-5 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground">
              <ShieldCheck className="h-5 w-5" aria-hidden />
            </div>
            <div className="min-w-0">
              <h1 className="text-sm font-extrabold text-foreground sm:text-base">Document Anonymizer</h1>
              <p className="mt-0.5 hidden text-xs text-muted-foreground sm:block">Protect personal and sensitive data (GDPR)</p>
            </div>
          </div>
          <Button
            variant="outline"
            size="icon"
            onClick={() => setDark((d) => !d)}
            aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
          >
            {dark ? <Sun aria-hidden /> : <Moon aria-hidden />}
          </Button>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-8 px-5 py-8 sm:px-8 sm:py-10">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="mb-3 text-xs font-bold uppercase text-primary">Document anonymization</p>
            <h2 className="text-2xl font-extrabold text-foreground sm:text-3xl">
              {showUpload ? "New document" : "Review anonymized version"}
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {showUpload
                ? "Upload a PDF or text file (up to 10 MB)."
                : "Approve the version or reject it with feedback to generate another."}
            </p>
          </div>
          <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-primary" />
            {isMockMode ? "Demo mode" : snapshot?.mode === "rules" ? "Connected · rules only" : "Connected to server"}
          </span>
        </div>

        {initialising ? (
          <div className="flex items-center justify-center gap-3 p-16 text-sm text-muted-foreground" role="status">
            <Loader2 className="h-5 w-5 animate-spin text-primary" aria-hidden /> Loading the current review...
          </div>
        ) : showUpload ? (
          <div className="flex flex-col gap-4">
            {wantsNew && (
              <Button variant="ghost" className="self-start" onClick={() => { setWantsNew(false); setError(null); }} disabled={uploading}>
                ← Back to current review
              </Button>
            )}
            <UploadStep
              file={file}
              onFile={(f) => { setFile(f); setError(null); }}
              onAnalyze={upload}
              loading={uploading}
              status={
                file && isAudioFile(file)
                  ? "Transcribing and censoring the audio... this can take several seconds."
                  : "Analyzing the document... (about 8 s)"
              }
              error={error}
              onRetry={() => (file ? void upload() : void load())}
              audioEnabled={snapshot?.audio_enabled ?? false}
            />
          </div>
        ) : (
          snapshot && (
            <ReviewWorkspace
              snapshot={snapshot}
              busy={busy}
              busyMessage={busyMessage}
              error={error}
              onRetry={retry}
              onReject={reject}
              onApprove={approve}
              onNewDocument={() => { setWantsNew(true); setError(null); setRetry(null); }}
            />
          )
        )}
      </main>

      <footer className="border-t border-border px-5 py-5 text-xs text-muted-foreground">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 sm:px-8">
          <span className="flex items-center gap-2"><LockKeyhole className="h-3.5 w-3.5" aria-hidden /> Data protection · GDPR</span>
          <span className="flex items-center gap-2">{isMockMode ? "Demo document with dummy data" : "Review connected to the server"}</span>
        </div>
      </footer>
    </div>
  );
}
