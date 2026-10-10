import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, ArrowUpRight, Check, CheckCheck, ChevronRight, CircleCheck, Clock3, FileCheck2, FileText, History, Info, LockKeyhole, Plus, ShieldCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";

type RejectedVersion = { attempt: number; text: string; reason: string };
type Snapshot = { has_document: boolean; attempt: number; text: string; approved: boolean; history: RejectedVersion[]; mode: string; warnings: number; issues: number };

const API = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

async function callApi(path: string, init?: RequestInit): Promise<Snapshot> {
  const res = await fetch(`${API}${path}`, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Não foi possível contactar o servidor.");
  return data as Snapshot;
}

// Removed local getMaskedText; we will use the Python backend API instead.

function MaskedLine({ line }: { line: string }) {
  return <p className="document-line">{line.split(/(\*(?:\/\*)*)/g).map((part, i) => part.includes("*") ? <span className="mask-token" key={i}>{part}</span> : <span key={i}>{part}</span>)}</p>;
}

export function ReviewWorkspace() {
  const [attempt, setAttempt] = useState(1);
  const [text, setText] = useState("");
  const [history, setHistory] = useState<RejectedVersion[]>([]);

  const [hasDocument, setHasDocument] = useState(false);
  const [mode, setMode] = useState("rules");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function show(data: Snapshot) {
    setHasDocument(data.has_document);
    setAttempt(data.attempt);
    setText(data.text);
    setHistory(data.history);
    setApproved(data.approved);
    setMode(data.mode);
  }

  useEffect(() => {
    callApi("/api/current")
      .then(data => { show(data); if (!data.has_document) setNewOpen(true); })
      .catch(err => { setText(""); setError(err.message); });
  }, []);
  const [approved, setApproved] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<RejectedVersion | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [newText, setNewText] = useState("");
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState("documento");
  const fileInput = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState("");
  const masks = (text.match(/\*/g) ?? []).length;

  async function reject() {
    setBusy(true);
    setError("");
    try {
      const data = await callApi("/api/reject", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ attempt, text, reason: reason.trim() }),
      });
      show(data);
      setReason("");
      setRejectOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro desconhecido.");
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    setError("");
    try {
      show(await callApi("/api/approve", { method: "POST" }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erro desconhecido.");
    }
  }

  async function startReview() {
    const body: BodyInit = pendingFile ?? newText;
    if (!pendingFile && !newText.trim()) return;
    const type = pendingFile?.name.toLowerCase().endsWith(".pdf") ? "application/pdf" : "text/plain; charset=utf-8";
    setBusy(true);
    setFileError("");
    try {
      show(await callApi("/api/document", { method: "POST", headers: { "Content-Type": type }, body }));
      setNewOpen(false);
      setPendingFile(null);
    } catch (err) {
      setFileError(err instanceof Error ? err.message : "Erro desconhecido.");
    } finally {
      setBusy(false);
    }
  }

  function download() {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "submission.txt";
    link.click();
    URL.revokeObjectURL(url);
  }

  return <>
    <header className="app-header">
      <div className="flex items-center">
        <div className="brand">
          <ShieldCheck className="brand-mark" strokeWidth={1.7} />
          <span>MiniNovers<span className="text-success"></span>
        </span>
        </div>
        <span className="brand-divider" />
        <span className="app-label">
          Proteção de dados
        </span>
      </div>
      <div className="session-label">
        <LockKeyhole size={13} />
        <span>Sessão local</span>
      </div>
    </header>
    <div className="workspace">
      <aside className="workflow-sidebar" aria-label="Etapas do documento">
        <span className="section-label">Documento</span>
        <div className="file-summary"><FileText size={20} /><div><strong>{fileName}</strong><small>{mode === "model" ? "Gemini + regras de segurança" : "Só regras de segurança"} · {text.length} caracteres</small></div></div>
        <span className="section-label">Processo de revisão</span>
        <ol className="workflow-steps">
          <li className="workflow-step done"><span className="step-icon"><Check size={13} /></span><div><strong>Texto recebido</strong><small>{hasDocument ? fileName : "Sem documento"}</small></div></li>
          <li className={`workflow-step ${approved ? "done" : "active"}`}><span className="step-icon">{approved ? <Check size={13} /> : "2"}</span><div><strong>Revisão manual</strong><small>{approved ? "Revisão concluída" : `Tentativa ${attempt}`}</small></div></li>
          <li className={`workflow-step ${approved ? "done" : ""}`}><span className="step-icon">{approved ? <Check size={13} /> : "3"}</span><div><strong>Aprovação final</strong><small>{approved ? "Documento aprovado" : "A aguardar revisão"}</small></div></li>
        </ol>
        <div className="sidebar-footer"><ShieldCheck size={16} /><span>Revisão de dados · RGPD</span></div>
      </aside>
      <main className="review-main">
        <div className="breadcrumb"><span>Documentos</span><ChevronRight size={12} /><span>Revisão manual</span></div>
        <div className="page-title-row"><div><h1>Revisão de anonimização</h1><p className="page-subtitle">{approved ? "A versão final do documento foi aprovada." : "Valide o documento antes da aprovação final."}</p></div><Button variant="outline" size="sm" onClick={() => { setNewText(""); setPendingFile(null); setFileError(""); setNewOpen(true); }}><Plus />Nova revisão</Button></div>
        <div className="review-grid">
          <section aria-label="Documento em revisão">
            <div className="document-frame" key={`${attempt}-${fileName}`}>
              <div className="document-toolbar"><div className="document-toolbar-title"><FileText size={16} /><span>Documento anonimizado</span></div><span className={`badge ${approved ? "approved" : "pending"}`}>{approved ? <CircleCheck size={11} /> : <Clock3 size={11} />}{approved ? "Aprovado" : "Em revisão"}</span></div>
              <div className="document-paper"><div className="paper-top"><span>Versão para revisão</span><span>Tentativa {String(attempt).padStart(2, "0")}</span></div><div className="document-lines">{text.split("\n").map((line, index) => <MaskedLine line={line} key={index} />)}</div></div>
              <div className="document-footer"><span>{text.split("\n").length} linhas · {text.length} caracteres</span><span>{masks} asteriscos</span></div>
            </div>
            <div className="decision-area" aria-live="polite">
              {approved ? <><div className="approved-message"><CheckCheck size={24} /><div><h2>Documento aprovado</h2><p>A revisão foi concluída. A versão final está pronta.</p></div></div><div className="decision-buttons"><Button variant="approve" onClick={download}><ArrowDownToLine />Descarregar texto final</Button></div></> : <><h2>O texto está corretamente anonimizado?</h2>{error && <p className="text-sm text-destructive" role="alert">{error}</p>}<p>Confirme que os dados sensíveis estão ocultos.</p><div className="decision-buttons"><Button variant="approve" onClick={approve}><Check size={16} />Aprovar versão</Button><Button variant="reject" onClick={() => setRejectOpen(true)}><X size={16} />Rejeitar versão</Button></div><div className="review-note"><Info size={12} /><span>As versões rejeitadas ficam no histórico desta sessão.</span></div></>}
            </div>
          </section>
          <aside aria-label="Histórico de versões">
            <div className="history-heading"><h2><History size={16} />Histórico de versões</h2><span className="history-count">{history.length + 1}</span></div>
            <div className="history-current"><strong>Tentativa {attempt} <span className="ml-1 text-muted-foreground font-normal">· atual</span></strong><small>{approved ? "Aprovada" : "Em revisão"}</small></div>
            {history.length === 0 ? <div className="empty-history"><History size={28} strokeWidth={1.3} /><p>Sem versões rejeitadas</p></div> : [...history].reverse().map(version => <div className="history-item" key={version.attempt}><div className="history-item-top"><strong>Tentativa {version.attempt}</strong><span className="text-destructive text-[10px]">Rejeitada</span></div><p>{version.reason || "Sem observações"}</p><Button variant="ghost" size="sm" onClick={() => setPreview(version)}>Ver versão<ArrowUpRight size={12} /></Button></div>)}
            <div className="session-info"><strong><Info size={13} />{mode === "model" ? "Gemini ligado" : "Só regras de segurança"}</strong>{mode === "model" ? "Ao rejeitar, as observações são enviadas ao modelo e é gerada uma nova versão." : "Sem o Gemini ligado só se aplicam as regras de segurança: as observações não alteram o texto."}<p className="mt-2">O histórico é eliminado ao atualizar a página ou iniciar uma nova revisão.</p></div>
          </aside>
        </div>
        <footer className="bottom-note"><span className="flex items-center gap-1.5"><LockKeyhole size={11} />O texto permanece nesta sessão do navegador.</span><span>Revisão manual de anonimização</span></footer>
      </main>
    </div>
    <Dialog open={rejectOpen} onOpenChange={setRejectOpen}><DialogContent><DialogTitle>Rejeitar tentativa {attempt}?</DialogTitle><DialogDescription>{mode === "model" ? "Esta versão fica no histórico. As observações são enviadas ao modelo, que gera uma nova tentativa (pode demorar cerca de um minuto)." : "Esta versão fica no histórico. Sem o Gemini ligado a nova tentativa será igual."}</DialogDescription><div><label className="modal-label" htmlFor="reason">Observações <span className="text-muted-foreground">(opcional)</span></label><Textarea id="reason" value={reason} onChange={event => setReason(event.target.value)} placeholder="Dados que ainda precisam de ser ocultos…" rows={3} /></div><div className="modal-actions"><Button variant="outline" onClick={() => setRejectOpen(false)}>Cancelar</Button><Button variant="destructive" disabled={busy} onClick={reject}><X />{busy ? "A gerar…" : "Confirmar rejeição"}</Button></div></DialogContent></Dialog>
    <Dialog open={preview !== null} onOpenChange={open => { if (!open) setPreview(null); }}><DialogContent><DialogTitle>Tentativa {preview?.attempt} · rejeitada</DialogTitle><DialogDescription>{preview?.reason || "Versão guardada sem observações."}</DialogDescription><pre className="preview-text">{preview?.text}</pre></DialogContent></Dialog>
    <Dialog open={newOpen} onOpenChange={setNewOpen}><DialogContent><DialogTitle>Nova revisão</DialogTitle><DialogDescription>Envie o documento original (PDF ou texto). É anonimizado e fica em revisão; a revisão atual e o seu histórico serão substituídos.</DialogDescription><input ref={fileInput} type="file" accept=".txt,.pdf,text/plain,application/pdf" className="hidden" onChange={async event => { const file = event.target.files?.[0]; if (!file) return; if (file.size > 10000000) { setFileError("Escolha um ficheiro com menos de 10 MB."); return; } try { if (file.name.toLowerCase().endsWith(".pdf")) { setPendingFile(file); setNewText(""); } else { setPendingFile(null); setNewText(await file.text()); } setFileName(file.name); setFileError(""); } catch { setFileError("Não foi possível ler o ficheiro."); } event.target.value = ""; }} /><Button variant="outline" onClick={() => fileInput.current?.click()}><FileText />Escolher ficheiro (.pdf ou .txt)</Button>{fileError && <p className="text-sm text-destructive" role="alert">{fileError}</p>}<div><label className="modal-label" htmlFor="new-text">Ou cole o texto original</label><Textarea id="new-text" value={newText} onChange={event => { setNewText(event.target.value); setPendingFile(null); setFileName("documento.txt"); }} rows={7} placeholder="Cole aqui o texto original…" /></div><div className="modal-actions"><Button variant="outline" onClick={() => setNewOpen(false)}>Cancelar</Button><Button disabled={busy || (!pendingFile && !newText.trim())} onClick={startReview}><FileCheck2 />{busy ? "A anonimizar…" : "Iniciar revisão"}</Button></div></DialogContent></Dialog>
  </>;
}