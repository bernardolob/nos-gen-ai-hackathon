import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, Check, CheckCheck, ChevronRight, CircleCheck, Clock3, FileCheck2, FileImage, FileText, Film, History, Info, LockKeyhole, Plus, RefreshCw, ShieldCheck, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { MediaReview, type MediaInfo, type MediaRegion } from "@/components/media-review";

type Kind = "text" | "image" | "video";
type RejectedVersion = { attempt: number; text: string; reason: string; regions?: number | null };
type Progress = { stage: string; completed: number; total: number };
type MediaModel = { id: string; capabilities: string[]; verified: true };
type Snapshot = {
  has_document: boolean; kind: Kind;
  status: "idle" | "processing" | "ready" | "exporting" | "failed" | "approved";
  progress: Progress; attempt: number; text: string; approved: boolean;
  history: RejectedVersion[]; mode: string; warnings: number; issues: number;
  media?: MediaInfo; regions?: MediaRegion[]; model?: MediaModel | null; error?: string;
};

const API = (import.meta.env["VITE_API_URL"]?.trim() || "http://127.0.0.1:8000").replace(/\/+$/, "");
const ACCEPT = ".txt,.pdf,.jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,text/plain,application/pdf,image/jpeg,image/png,image/webp,video/mp4,video/quicktime,video/webm";

async function callApi(path: string, init?: RequestInit): Promise<Snapshot> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, init);
  } catch {
    throw new Error(`Não foi possível ligar ao servidor em ${API}. Confirme que o backend está iniciado e que VITE_API_URL usa a mesma porta.`);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Não foi possível contactar o servidor.");
  return data as Snapshot;
}

function MaskedLine({ line }: { line: string }) {
  return <p className="document-line">{line.split(/(\*(?:\/\*)*)/g).map((part, i) => part.includes("*") ? <span className="mask-token" key={i}>{part}</span> : <span key={i}>{part}</span>)}</p>;
}

function mimeFor(file: File): string {
  if (file.type) return file.type;
  const extension = file.name.toLowerCase().split(".").pop();
  return ({ txt: "text/plain", pdf: "application/pdf", jpg: "image/jpeg", jpeg: "image/jpeg", png: "image/png", webp: "image/webp", mp4: "video/mp4", mov: "video/quicktime", webm: "video/webm" } as Record<string, string>)[extension ?? ""] ?? "application/octet-stream";
}

function fileLimit(type: string): number {
  if (type.startsWith("video/")) return 100_000_000;
  if (type.startsWith("image/")) return 20_000_000;
  return 10_000_000;
}

export function ReviewWorkspace() {
  const [snapshot, setSnapshot] = useState<Snapshot>({ has_document: false, kind: "text", status: "idle", progress: { stage: "", completed: 0, total: 0 }, attempt: 1, text: "", approved: false, history: [], mode: "rules", warnings: 0, issues: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<RejectedVersion | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [newText, setNewText] = useState("");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState("documento");
  const [fileError, setFileError] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const { attempt, text, history, approved, kind, status, progress } = snapshot;
  const masks = (text.match(/\*/g) ?? []).length;
  const processing = status === "processing" || status === "exporting";

  useEffect(() => {
    callApi("/api/current").then(data => { setSnapshot(data); if (!data.has_document) setNewOpen(true); }).catch(err => setError(err.message));
  }, []);
  useEffect(() => {
    if (!processing) return;
    const timer = window.setInterval(() => { callApi("/api/current").then(setSnapshot).catch(err => setError(err.message)); }, 900);
    return () => window.clearInterval(timer);
  }, [processing]);

  async function reject() {
    setBusy(true); setError("");
    try {
      setSnapshot(await callApi("/api/reject", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ attempt, text, reason: reason.trim() }) }));
      setReason(""); setRejectOpen(false);
    } catch (err) { setError(err instanceof Error ? err.message : "Erro desconhecido."); }
    finally { setBusy(false); }
  }
  async function approve() {
    setError("");
    try { setSnapshot(await callApi("/api/approve", { method: "POST" })); }
    catch (err) { setError(err instanceof Error ? err.message : "Erro desconhecido."); }
  }
  function chooseFile(file: File) {
    const type = mimeFor(file);
    if (!ACCEPT.includes(type) && !ACCEPT.includes(`.${file.name.toLowerCase().split(".").pop()}`)) { setFileError("Formato não suportado."); return; }
    if (file.size > fileLimit(type)) { setFileError(type.startsWith("video/") ? "Escolha um vídeo com menos de 100 MB." : type.startsWith("image/") ? "Escolha uma imagem com menos de 20 MB." : "Escolha um documento com menos de 10 MB."); return; }
    setPendingFile(file); setNewText(""); setFileName(file.name); setFileError("");
  }
  async function startReview() {
    if (!pendingFile && !newText.trim()) return;
    const body: BodyInit = pendingFile ?? newText;
    const type = pendingFile ? mimeFor(pendingFile) : "text/plain; charset=utf-8";
    setBusy(true); setFileError("");
    try {
      const headers: Record<string, string> = { "Content-Type": type };
      if (pendingFile) headers["X-File-Name"] = encodeURIComponent(pendingFile.name);
      setSnapshot(await callApi("/api/document", { method: "POST", headers, body }));
      setError("");
      setNewOpen(false); setPendingFile(null);
    } catch (err) { setFileError(err instanceof Error ? err.message : "Erro desconhecido."); }
    finally { setBusy(false); }
  }
  async function saveRegions(regions: MediaRegion[]) {
    setError("");
    try { setSnapshot(await callApi("/api/media/regions", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ attempt, regions }) })); }
    catch (err) { setError(err instanceof Error ? err.message : "Erro desconhecido."); throw err; }
  }
  async function trackRegion(region: MediaRegion, seedTimeMs: number): Promise<MediaRegion> {
    setError("");
    const res = await fetch(`${API}/api/media/track`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ attempt, seed_time_ms: seedTimeMs, region }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const message = typeof data.detail === "string" ? data.detail : "Não foi possível rastrear a caixa.";
      setError(message);
      throw new Error(message);
    }
    return data as MediaRegion;
  }
  function download() {
    if (kind !== "text" && snapshot.media?.output_url) { window.location.assign(`${API}${snapshot.media.output_url}`); return; }
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const link = document.createElement("a"); link.href = url; link.download = "submission.txt"; link.click(); URL.revokeObjectURL(url);
  }

  const mediaLabel = kind === "image" ? "Imagem" : kind === "video" ? "Vídeo" : "Documento";
  const mediaIcon = kind === "image" ? <FileImage size={20} /> : kind === "video" ? <Film size={20} /> : <FileText size={20} />;

  return <>
    <header className="app-header"><div className="flex items-center"><div className="brand"><ShieldCheck className="brand-mark" strokeWidth={1.7} /><span>MiniNovers</span></div><span className="brand-divider" /><span className="app-label">Proteção de dados</span></div><div className="session-label"><LockKeyhole size={13} /><span>Sessão local</span></div></header>
    <div className="workspace"><aside className="workflow-sidebar" aria-label="Etapas da revisão"><span className="section-label">{mediaLabel}</span><div className="file-summary">{mediaIcon}<div><strong>{fileName}</strong><small>{kind === "text" ? `${snapshot.mode === "model" ? "Gemini + regras" : "Regras de segurança"} · ${text.length} caracteres` : `${snapshot.model?.id ?? "Modelo multimodal"} · ${snapshot.regions?.length ?? 0} regiões`}</small></div></div><span className="section-label">Processo de revisão</span><ol className="workflow-steps"><li className="workflow-step done"><span className="step-icon"><Check size={13} /></span><div><strong>Ficheiro recebido</strong><small>{snapshot.has_document ? fileName : "Sem ficheiro"}</small></div></li><li className={`workflow-step ${approved ? "done" : "active"}`}><span className="step-icon">{approved ? <Check size={13} /> : "2"}</span><div><strong>{processing ? "A processar" : "Revisão manual"}</strong><small>Tentativa {attempt}</small></div></li><li className={`workflow-step ${approved ? "done" : ""}`}><span className="step-icon">{approved ? <Check size={13} /> : "3"}</span><div><strong>Aprovação final</strong><small>{approved ? "Ficheiro aprovado" : "A aguardar revisão"}</small></div></li></ol><div className="sidebar-footer"><ShieldCheck size={16} /><span>Revisão de dados · RGPD</span></div></aside>
      <main className="review-main"><div className="breadcrumb"><span>Ficheiros</span><ChevronRight size={12} /><span>Revisão manual</span></div><div className="page-title-row"><div><h1>Revisão de anonimização</h1><p className="page-subtitle">{approved ? "A versão final foi aprovada." : processing ? `${progress.stage || "A processar…"}` : "Valide todas as ocultações antes da aprovação final."}</p></div><Button variant="outline" size="sm" onClick={() => { setNewText(""); setPendingFile(null); setFileError(""); setNewOpen(true); }}><Plus />Nova revisão</Button></div>
        <div className="review-grid"><section aria-label="Ficheiro em revisão"><div className="document-frame"><div className="document-toolbar"><div className="document-toolbar-title">{mediaIcon}<span>{mediaLabel} anonimizado</span></div><span className={`badge ${approved ? "approved" : "pending"}`}>{approved ? <CircleCheck size={11} /> : <Clock3 size={11} />}{approved ? "Aprovado" : processing ? "A processar" : "Em revisão"}</span></div>
          {kind === "text" ? <><div className="document-paper"><div className="paper-top"><span>Versão para revisão</span><span>Tentativa {String(attempt).padStart(2, "0")}</span></div><div className="document-lines">{text.split("\n").map((line, index) => <MaskedLine line={line} key={index} />)}</div></div><div className="document-footer"><span>{text.split("\n").length} linhas · {text.length} caracteres</span><span>{masks} asteriscos</span></div></> : processing ? <div className="processing-panel"><RefreshCw className="spin" /><strong>{progress.stage || "A preparar análise multimodal…"}</strong><progress max={Math.max(1, progress.total)} value={progress.completed} /></div> : status === "failed" ? <div className="processing-panel error-panel"><X /><strong>A análise falhou</strong><p>{snapshot.error || "Não foi possível processar o ficheiro."}</p></div> : snapshot.media ? <MediaReview api={API} attempt={attempt} kind={kind} media={snapshot.media} regions={snapshot.regions ?? []} onSave={saveRegions} onTrack={trackRegion} disabled={approved} /> : null}</div>
          <div className="decision-area" aria-live="polite">{approved ? <><div className="approved-message"><CheckCheck size={24} /><div><h2>Ficheiro aprovado</h2><p>A versão anonimizada está pronta.</p></div></div><div className="decision-buttons"><Button variant="approve" onClick={download}><ArrowDownToLine />Descarregar versão final</Button></div></> : <><h2>{kind === "text" ? "O texto está corretamente anonimizado?" : "Todas as regiões sensíveis estão cobertas?"}</h2>{error && <p className="text-sm text-destructive" role="alert">{error}</p>}<p>{kind === "text" ? "Confirme que os dados sensíveis estão ocultos." : "Adicione ou ajuste regiões antes de aprovar. As regiões ficam fortemente pixelizadas no ficheiro final."}</p><div className="decision-buttons"><Button variant="approve" disabled={processing || status === "failed"} onClick={approve}><Check size={16} />Aprovar versão</Button><Button variant="reject" disabled={processing} onClick={() => setRejectOpen(true)}><X size={16} />{kind === "text" ? "Rejeitar versão" : "Reanalisar"}</Button></div><div className="review-note"><Info size={12} /><span>As versões rejeitadas ficam no histórico desta sessão.</span></div></>}</div></section>
          <aside aria-label="Histórico de versões"><div className="history-heading"><h2><History size={16} />Histórico</h2><span className="history-count">{history.length + 1}</span></div><div className="history-current"><strong>Tentativa {attempt} <span className="ml-1 text-muted-foreground font-normal">· atual</span></strong><small>{approved ? "Aprovada" : processing ? "Em processamento" : "Em revisão"}</small></div>{history.length === 0 ? <div className="empty-history"><History size={28} strokeWidth={1.3} /><p>Sem versões rejeitadas</p></div> : [...history].reverse().map(version => <div className="history-item" key={version.attempt}><div className="history-item-top"><strong>Tentativa {version.attempt}</strong><span className="text-destructive text-[10px]">Rejeitada</span></div><p>{version.reason || "Sem observações"}</p>{kind === "text" ? <Button variant="ghost" size="sm" onClick={() => setPreview(version)}>Ver versão</Button> : <small>{version.regions ?? 0} regiões</small>}</div>)}<div className="session-info"><strong><Info size={13} />{kind === "text" ? (snapshot.mode === "model" ? "Gemini ligado" : "Só regras de segurança") : snapshot.model?.verified ? "Modelo multimodal verificado" : "A verificar modelo"}</strong>{kind !== "text" && snapshot.model ? <><span>{snapshot.model.id}</span><br /><span>{snapshot.model.capabilities.join(" · ")}</span></> : null}<p className="mt-2">Os ficheiros são temporários. Na análise automática, amostras visuais são enviadas ao modelo Gemini configurado.</p></div></aside></div>
        <footer className="bottom-note"><span className="flex items-center gap-1.5"><LockKeyhole size={11} />Armazenamento temporário nesta sessão local.</span><span>Revisão manual de anonimização</span></footer></main></div>
    <Dialog open={rejectOpen} onOpenChange={setRejectOpen}><DialogContent><DialogTitle>{kind === "text" ? `Rejeitar tentativa ${attempt}?` : `Reanalisar tentativa ${attempt}?`}</DialogTitle><DialogDescription>As observações serão enviadas ao modelo para gerar uma nova tentativa.</DialogDescription><div><label className="modal-label" htmlFor="reason">Observações <span className="text-muted-foreground">(opcional)</span></label><Textarea id="reason" value={reason} onChange={event => setReason(event.target.value)} placeholder="Ex.: oculta também a morada no canto inferior direito…" rows={3} /></div><div className="modal-actions"><Button variant="outline" onClick={() => setRejectOpen(false)}>Cancelar</Button><Button variant="destructive" disabled={busy} onClick={reject}><RefreshCw />{busy ? "A iniciar…" : "Confirmar"}</Button></div></DialogContent></Dialog>
    <Dialog open={preview !== null} onOpenChange={open => { if (!open) setPreview(null); }}><DialogContent><DialogTitle>Tentativa {preview?.attempt} · rejeitada</DialogTitle><DialogDescription>{preview?.reason || "Versão guardada sem observações."}</DialogDescription><pre className="preview-text">{preview?.text}</pre></DialogContent></Dialog>
    <Dialog open={newOpen} onOpenChange={setNewOpen}><DialogContent><DialogTitle>Nova revisão</DialogTitle><DialogDescription>Arraste ou escolha um documento, uma fotografia ou um vídeo. A revisão atual e o histórico serão substituídos.</DialogDescription><input ref={fileInput} type="file" accept={ACCEPT} className="hidden" onChange={event => { const file = event.target.files?.[0]; if (file) chooseFile(file); event.target.value = ""; }} /><div className={`upload-dropzone ${dragging ? "dragging" : ""}`} role="button" tabIndex={0} onClick={() => fileInput.current?.click()} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") fileInput.current?.click(); }} onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); const file = event.dataTransfer.files[0]; if (file) chooseFile(file); }}><Upload /><strong>{pendingFile ? pendingFile.name : "Largue o ficheiro aqui"}</strong><span>ou clique para escolher</span><small>PDF, TXT, JPG, PNG, WEBP, MP4, MOV ou WEBM</small>{pendingFile && <small>{mimeFor(pendingFile)} · {(pendingFile.size / 1_000_000).toFixed(1)} MB</small>}</div>{fileError && <p className="text-sm text-destructive" role="alert">{fileError}</p>}<div><label className="modal-label" htmlFor="new-text">Ou cole o texto original</label><Textarea id="new-text" value={newText} onChange={event => { setNewText(event.target.value); setPendingFile(null); setFileName("documento.txt"); }} rows={5} placeholder="Cole aqui o texto original…" /></div><div className="modal-actions"><Button variant="outline" onClick={() => setNewOpen(false)}>Cancelar</Button><Button disabled={busy || (!pendingFile && !newText.trim())} onClick={startReview}><FileCheck2 />{busy ? "A enviar…" : "Iniciar revisão"}</Button></div></DialogContent></Dialog>
  </>;
}
