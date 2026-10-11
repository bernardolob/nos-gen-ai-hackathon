import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState, type CSSProperties } from "react";
import { Info, Loader2, LockKeyhole, Moon, ShieldCheck, Sun } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { UploadStep } from "@/components/anonymizer/steps";
import { ReviewWorkspace } from "@/components/review/workspace";
import {
  approveVersion,
  getCurrent,
  isAudioFile,
  isMediaFile,
  isMockMode,
  isVideoFile,
  isWorking,
  rejectVersion,
  uploadFile,
  waitUntilSettled,
  wasSampleSubstituted,
} from "@/lib/review/api";
import { ApiError, type Progress, type Snapshot } from "@/lib/review/types";

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
  const [progress, setProgress] = useState<Progress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState<(() => void) | null>(null);
  const [dark, setDark] = useState(false);
  const [sampleNotice, setSampleNotice] = useState(false);

  // The theme script in <head> already set the class; read it back, then keep both in step.
  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);
  const toggleTheme = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      /* private mode: the choice just is not remembered */
    }
  };

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
    setProgress(null);
    try {
      let result = await uploadFile(file);
      if (isWorking(result)) {
        if (result.progress) setProgress(result.progress);
        result = await waitUntilSettled((s) => {
          setProgress(s.progress);
        });
      }
      if (result.status === "failed") {
        throw new Error(result.error || "The file could not be analyzed.");
      }
      setSnapshot(result);
      setSampleNotice(isMockMode && wasSampleSubstituted());
      setFile(null);
      setWantsNew(false);
    } catch (e) {
      setError(message(e));
    } finally {
      setUploading(false);
      setProgress(null);
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
      <header className="sticky top-0 z-50 border-b border-border bg-background/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 w-full max-w-[1180px] items-center justify-between gap-4 px-4 sm:h-16 sm:px-6">
          <div className="flex min-w-0 items-center gap-2 text-lg font-bold text-foreground">
            <span className="brand-gradient h-[22px] w-[22px] shrink-0 rounded-md" aria-hidden />
            MiniNovers
          </div>
          <div className="flex items-center gap-2.5">
            <span className="flex items-center gap-1.5 rounded-full border border-border bg-card px-3 py-1.5 text-xs text-muted-foreground sm:text-[13px]">
              <ShieldCheck className="h-4 w-4 text-ok" aria-hidden />
              <span className="max-[420px]:sr-only">Data protection · GDPR</span>
            </span>
            <Button
              variant="outline"
              size="icon"
              className="rounded-full bg-card"
              onClick={toggleTheme}
              aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
            >
              {dark ? <Sun aria-hidden /> : <Moon aria-hidden />}
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-[1180px] flex-1 flex-col px-4 sm:px-6">
        {showUpload ? (
          <section className="hero-glow pb-12 pt-12 text-center sm:pb-16 sm:pt-20">
            <span className="reveal mb-6 inline-block rounded-full border border-border bg-card px-3.5 py-1.5 text-xs text-muted-foreground sm:text-[13px]">
              ✨ Privacy by design · {isMockMode ? "Demo mode" : snapshot?.mode === "rules" ? "Connected · rules only" : "Connected to server"}
            </span>
            <h1 className="gradient-text reveal mx-auto mb-5 max-w-[780px] text-[clamp(2.3rem,6vw,4rem)] font-bold leading-[1.06] tracking-[-0.035em]" style={{ "--d": "0.1s" } as CSSProperties}>
              Share the document, not the data.
            </h1>
            <p className="reveal mx-auto max-w-[520px] text-[1.05rem] text-muted-foreground" style={{ "--d": "0.2s" } as CSSProperties}>
              Documents, audio, photos and videos, anonymized in seconds. Every redaction is yours to review before it is final.
            </p>

            <div className="reveal mx-auto mt-10 max-w-[640px] text-left" style={{ "--d": "0.3s" } as CSSProperties}>
              {initialising ? (
                <div className="flex items-center justify-center gap-3 p-16 text-sm text-muted-foreground" role="status">
                  <Loader2 className="h-5 w-5 animate-spin text-brand" aria-hidden /> Loading the current review...
                </div>
              ) : (
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
                        : file && isVideoFile(file)
                        ? "Analyzing video frames... this can take a while."
                        : file && isMediaFile(file)
                        ? "Analyzing image... (about 5 s)"
                        : "Analyzing the document... (about 8 s)"
                    }
                    progress={progress}
                    error={error}
                    errorTitle={
                      file
                        ? isMediaFile(file)
                          ? isVideoFile(file)
                            ? "The video could not be analyzed"
                            : "The image could not be analyzed"
                          : "The document could not be analyzed"
                        : "Could not load the current review"
                    }
                    onRetry={() => (file ? void upload() : void load())}
                    audioEnabled={snapshot?.audio_enabled ?? false}
                  />
                </div>
              )}
            </div>
          </section>
        ) : (
          snapshot && (
            <section className="pb-16 pt-8 sm:pt-11">
              <div className="reveal mb-8 flex flex-wrap items-start justify-between gap-4">
                <div>
                  <h2 className="text-[clamp(1.6rem,4vw,2.7rem)] font-bold leading-[1.1] tracking-[-0.03em] text-foreground">
                    Anonymization review
                  </h2>
                  <p className="mt-1.5 text-sm text-muted-foreground sm:text-base">
                    Approve the version or reject it with feedback to generate another.
                  </p>
                </div>
                <span className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <span className="h-1.5 w-1.5 rounded-full bg-ok" />
                  {isMockMode ? "Demo mode" : snapshot.mode === "rules" ? "Connected · rules only" : "Connected to server"}
                </span>
              </div>
              {sampleNotice && (
                <Alert className="mb-6">
                  <Info className="h-4 w-4" aria-hidden />
                  <AlertDescription>
                    Demo mode cannot read this file's content in the browser, so this is a sample
                    result, not your document. Connect <code>VITE_API_URL</code> to a real backend
                    to analyze actual files.
                  </AlertDescription>
                </Alert>
              )}
              <ReviewWorkspace
                snapshot={snapshot}
                busy={busy}
                busyMessage={busyMessage}
                error={error}
                onRetry={retry}
                onReject={reject}
                onApprove={approve}
                onNewDocument={() => {
                  setWantsNew(true);
                  setError(null);
                  setRetry(null);
                  setSampleNotice(false);
                }}
              />
            </section>
          )
        )}
      </main>

      <footer className="border-t border-border px-4 py-5 text-xs text-muted-foreground sm:px-6">
        <div className="mx-auto flex max-w-[1180px] flex-wrap items-center justify-between gap-3">
          <span className="flex items-center gap-2"><LockKeyhole className="h-3.5 w-3.5" aria-hidden /> Data protection · GDPR</span>
          <span className="flex items-center gap-2">{isMockMode ? "Demo document with dummy data" : "Review connected to the server"}</span>
        </div>
      </footer>
    </div>
  );
}
