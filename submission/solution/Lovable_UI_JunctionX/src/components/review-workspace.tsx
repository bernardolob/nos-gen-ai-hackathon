import { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, ArrowUpRight, Check, CheckCheck, ChevronRight, CircleCheck, Clock3, FileCheck2, FileText, History, Info, LockKeyhole, Plus, ShieldCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";

type RejectedVersion = { attempt: number; text: string; reason: string };

// Removed local getMaskedText; we will use the Python backend API instead.

function MaskedLine({ line }: { line: string }) {
  return <p className="document-line">{line.split(/(\*(?:\/\*)*)/g).map((part, i) => part.includes("*") ? <span className="mask-token" key={i}>{part}</span> : <span key={i}>{part}</span>)}</p>;
}

export function ReviewWorkspace() {
  const [attempt, setAttempt] = useState(1);
  const [text, setText] = useState("Carregando...");
  const [history, setHistory] = useState<RejectedVersion[]>([]);

  useEffect(() => {
    fetch("http://localhost:8000/api/current")
      .then(res => res.json())
      .then(data => {
        setAttempt(data.attempt);
        setText(data.text);
        setHistory(data.history);
      })
      .catch(err => console.error("API error:", err));
  }, []);
  const [approved, setApproved] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<RejectedVersion | null>(null);
  const [newOpen, setNewOpen] = useState(false);
  const [newText, setNewText] = useState("");
  const [source, setSource] = useState("demo");
  const [fileName, setFileName] = useState("relatorio_admissao.txt");
  const fileInput = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState("");
  const masks = (text.match(/\*/g) ?? []).length;

  function reject() {
    fetch("http://localhost:8000/api/reject", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ attempt, text, reason: reason.trim() })
    })
      .then(res => res.json())
      .then(data => {
        setAttempt(data.attempt);
        if (source === "demo") setText(data.text);
        setHistory(data.history);
        setReason("");
        setRejectOpen(false);
      })
      .catch(err => console.error(err));
  }

  function startReview() {
    if (!newText.trim()) return;
    setText(newText.trim());
    setAttempt(1);
    setHistory([]);
    setApproved(false);
    setSource("imported");
    setNewOpen(false);
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
        <div className="file-summary"><FileText size={20} /><div><strong>{fileName}</strong><small>Texto anonimizado · {text.length} caracteres</small></div></div>
        <span className="section-label">Processo de revisão</span>
        <ol className="workflow-steps">
          <li className="workflow-step done"><span className="step-icon"><Check size={13} /></span><div><strong>Texto recebido</strong><small>{source === "demo" ? "Documento de exemplo" : "Texto importado"}</small></div></li>
          <li className={`workflow-step ${approved ? "done" : "active"}`}><span className="step-icon">{approved ? <Check size={13} /> : "2"}</span><div><strong>Revisão manual</strong><small>{approved ? "Revisão concluída" : `Tentativa ${attempt}`}</small></div></li>
          <li className={`workflow-step ${approved ? "done" : ""}`}><span className="step-icon">{approved ? <Check size={13} /> : "3"}</span><div><strong>Aprovação final</strong><small>{approved ? "Documento aprovado" : "A aguardar revisão"}</small></div></li>
        </ol>
        <div className="sidebar-footer"><ShieldCheck size={16} /><span>Revisão de dados · RGPD</span></div>
      </aside>
      <main className="review-main">
        <div className="breadcrumb"><span>Documentos</span><ChevronRight size={12} /><span>Revisão manual</span></div>
        <div className="page-title-row"><div><h1>Revisão de anonimização</h1><p className="page-subtitle">{approved ? "A versão final do documento foi aprovada." : "Valide o documento antes da aprovação final."}</p></div><Button variant="outline" size="sm" onClick={() => { setNewText(""); setFileError(""); setNewOpen(true); }}><Plus />Nova revisão</Button></div>
        <div className="review-grid">
          <section aria-label="Documento em revisão">
            <div className="document-frame" key={`${attempt}-${source}`}>
              <div className="document-toolbar"><div className="document-toolbar-title"><FileText size={16} /><span>Documento anonimizado</span></div><span className={`badge ${approved ? "approved" : "pending"}`}>{approved ? <CircleCheck size={11} /> : <Clock3 size={11} />}{approved ? "Aprovado" : "Em revisão"}</span></div>
              <div className="document-paper"><div className="paper-top"><span>Versão para revisão</span><span>Tentativa {String(attempt).padStart(2, "0")}</span></div><div className="document-lines">{text.split("\n").map((line, index) => <MaskedLine line={line} key={index} />)}</div></div>
              <div className="document-footer"><span>{text.split("\n").length} linhas · {text.length} caracteres</span><span>{masks} asteriscos</span></div>
            </div>
            <div className="decision-area" aria-live="polite">
              {approved ? <><div className="approved-message"><CheckCheck size={24} /><div><h2>Documento aprovado</h2><p>A revisão foi concluída. A versão final está pronta.</p></div></div><div className="decision-buttons"><Button variant="approve" onClick={download}><ArrowDownToLine />Descarregar texto final</Button></div></> : <><h2>O texto está corretamente anonimizado?</h2><p>Confirme que os dados sensíveis estão ocultos.</p><div className="decision-buttons"><Button variant="approve" onClick={() => setApproved(true)}><Check size={16} />Aprovar versão</Button><Button variant="reject" onClick={() => setRejectOpen(true)}><X size={16} />Rejeitar versão</Button></div><div className="review-note"><Info size={12} /><span>As versões rejeitadas ficam no histórico desta sessão.</span></div></>}
            </div>
          </section>
          <aside aria-label="Histórico de versões">
            <div className="history-heading"><h2><History size={16} />Histórico de versões</h2><span className="history-count">{history.length + 1}</span></div>
            <div className="history-current"><strong>Tentativa {attempt} <span className="ml-1 text-muted-foreground font-normal">· atual</span></strong><small>{approved ? "Aprovada" : "Em revisão"}</small></div>
            {history.length === 0 ? <div className="empty-history"><History size={28} strokeWidth={1.3} /><p>Sem versões rejeitadas</p></div> : [...history].reverse().map(version => <div className="history-item" key={version.attempt}><div className="history-item-top"><strong>Tentativa {version.attempt}</strong><span className="text-destructive text-[10px]">Rejeitada</span></div><p>{version.reason || "Sem observações"}</p><Button variant="ghost" size="sm" onClick={() => setPreview(version)}>Ver versão<ArrowUpRight size={12} /></Button></div>)}
            <div className="session-info"><strong><Info size={13} />{source === "demo" ? "Modo de demonstração" : "Revisão local"}</strong>{source === "demo" ? "Texto de exemplo do user_review.py. Novas tentativas são simuladas." : "A geração automática não está ligada. Ao rejeitar, o texto mantém-se até importar uma nova versão."}<p className="mt-2">O histórico é eliminado ao atualizar a página ou iniciar uma nova revisão.</p></div>
          </aside>
        </div>
        <footer className="bottom-note"><span className="flex items-center gap-1.5"><LockKeyhole size={11} />O texto permanece nesta sessão do navegador.</span><span>Revisão manual de anonimização</span></footer>
      </main>
    </div>
    <Dialog open={rejectOpen} onOpenChange={setRejectOpen}><DialogContent><DialogTitle>Rejeitar tentativa {attempt}?</DialogTitle><DialogDescription>{source === "demo" ? "Esta versão será guardada no histórico e será iniciada uma nova tentativa simulada." : "Esta versão será guardada no histórico. A próxima tentativa mantém o mesmo texto porque a geração automática ainda não está ligada."}</DialogDescription><div><label className="modal-label" htmlFor="reason">Observações <span className="text-muted-foreground">(opcional)</span></label><Textarea id="reason" value={reason} onChange={event => setReason(event.target.value)} placeholder="Dados que ainda precisam de ser ocultos…" rows={3} /></div><div className="modal-actions"><Button variant="outline" onClick={() => setRejectOpen(false)}>Cancelar</Button><Button variant="destructive" onClick={reject}><X />Confirmar rejeição</Button></div></DialogContent></Dialog>
    <Dialog open={preview !== null} onOpenChange={open => { if (!open) setPreview(null); }}><DialogContent><DialogTitle>Tentativa {preview?.attempt} · rejeitada</DialogTitle><DialogDescription>{preview?.reason || "Versão guardada sem observações."}</DialogDescription><pre className="preview-text">{preview?.text}</pre></DialogContent></Dialog>
    <Dialog open={newOpen} onOpenChange={setNewOpen}><DialogContent><DialogTitle>Nova revisão</DialogTitle><DialogDescription>Importe um texto já anonimizado. A revisão atual e o seu histórico serão substituídos.</DialogDescription><input ref={fileInput} type="file" accept=".txt,text/plain" className="hidden" onChange={async event => { const file = event.target.files?.[0]; if (!file) return; if (file.size > 1000000) { setFileError("Escolha um ficheiro de texto com menos de 1 MB."); return; } try { setNewText(await file.text()); setFileName(file.name); setFileError(""); } catch { setFileError("Não foi possível ler o ficheiro."); } event.target.value = ""; }} /><Button variant="outline" onClick={() => fileInput.current?.click()}><FileText />Importar ficheiro .txt</Button>{fileError && <p className="text-sm text-destructive" role="alert">{fileError}</p>}<div><label className="modal-label" htmlFor="new-text">Texto anonimizado</label><Textarea id="new-text" value={newText} onChange={event => { setNewText(event.target.value); setFileName("documento.txt"); }} rows={7} placeholder="Cole aqui o texto a rever…" /></div><div className="modal-actions"><Button variant="outline" onClick={() => setNewOpen(false)}>Cancelar</Button><Button disabled={!newText.trim()} onClick={startReview}><FileCheck2 />Iniciar revisão</Button></div></DialogContent></Dialog>
  </>;
}