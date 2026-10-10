import { useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  ClipboardCheck,
  FileCheck2,
  LockKeyhole,
  Plus,
  ScanLine,
  AlertTriangle,
  Check,
  Copy,
  Download,
  Eye,
  EyeOff,
  FileText,
  Loader2,
  Upload,
} from "lucide-react";

import { Button } from "@/components/ui/button";

import {
  CATEGORIES,
  CONFIDENCE_LABELS,
  categoryById,
  type AnonymizeResponse,
  type AnalyzeResponse,
  type CategoryId,
  type Confidence,
  type Decision,
  type SensitiveItem,
} from "@/lib/anonymizer/types";

export const STEPS = ["Carregar", "Rever", "Resultado", "Relatório"] as const;

export function Stepper({ current }: { current: number }) {
  const icons = [Upload, ScanLine, FileCheck2, ClipboardCheck];
  return (
    <ol className="grid w-full grid-cols-4 border-b border-border" aria-label="Progresso">
      {STEPS.map((label, i) => {
        const n = i + 1;
        const done = n < current;
        const active = n === current;
        const Icon = icons[i] ?? Upload;
        return (
          <li key={label} aria-current={active ? "step" : undefined} className={`flex min-w-0 items-center justify-center gap-2 border-b-2 px-1 pb-4 sm:justify-start sm:gap-3 sm:px-3 ${active ? "border-primary text-primary" : "border-transparent text-muted-foreground"}`}>
            <span className={`hidden h-8 w-8 shrink-0 items-center justify-center rounded-md min-[420px]:flex ${active || done ? "bg-accent text-primary" : "bg-muted text-muted-foreground"}`}>
              {done ? <Check className="h-4 w-4" aria-hidden /> : <Icon className="h-4 w-4" aria-hidden />}
            </span>
            <span className="text-xs font-semibold sm:text-sm"><span className="mr-1 hidden text-muted-foreground lg:inline">0{n}</span>{label}</span>
          </li>
        );
      })}
    </ol>
  );
}

/* ---------------- Passo 1: Carregar ---------------- */

export function UploadStep({
  file,
  onFile,
  onAnalyze,
  loading,
  status,
  error,
  onRetry,
}: {
  file: File | null;
  onFile: (f: File | null) => void;
  onAnalyze: () => void;
  loading: boolean;
  status: string;
  error: string | null;
  onRetry: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  const accept = (f: File | undefined) => {
    if (f) onFile(f);
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center gap-4 rounded-lg border border-border bg-card p-16 text-center">
        <Loader2 className="h-10 w-10 animate-spin text-primary" aria-hidden />
        <p className="text-lg font-medium text-foreground" role="status">
          {status}
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
        <Button variant="ghost"
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
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); accept(e.dataTransfer.files?.[0]); }}
          className={`flex min-h-[300px] flex-col items-center justify-center gap-5 rounded-lg border border-dashed px-5 py-10 text-center transition-colors ${dragOver ? "border-primary bg-accent" : "border-input bg-card"}`}
        >
          <div className="relative grid h-16 w-16 place-items-center rounded-lg border border-border bg-background text-primary">
            <FileText className="h-7 w-7" strokeWidth={1.5} aria-hidden />
            <span className="absolute -bottom-2 -right-2 grid h-6 w-6 place-items-center rounded-full border-2 border-card bg-primary text-primary-foreground"><Plus className="h-3 w-3" aria-hidden /></span>
          </div>
          {file ? (
            <div className="max-w-full">
              <p className="break-all text-base font-semibold text-foreground">{file.name}</p>
              <p className="mt-1 text-xs text-muted-foreground">{(file.size / 1024).toFixed(1)} KB · Ready to analyze</p>
            </div>
          ) : (
            <div>
              <p className="text-base font-semibold text-foreground">Drag and drop your document here</p>
              <p className="mt-2 text-sm text-muted-foreground">PDF, text or Markdown</p>
            </div>
          )}
          <input ref={inputRef} type="file" accept=".pdf,.txt,.md" className="sr-only" onChange={(e) => accept(e.target.files?.[0])} />
          <Button variant="outline" onClick={() => inputRef.current?.click()}><Upload aria-hidden />{file ? "Choose another file" : "Choose file"}</Button>
        </div>
        <div className="mt-5 flex flex-wrap items-center justify-between gap-4">
          <span className="flex items-center gap-2 text-xs text-muted-foreground"><LockKeyhole className="h-3.5 w-3.5" aria-hidden /> Personal and sensitive data · GDPR</span>
          <Button onClick={onAnalyze} disabled={!file} className="h-11 px-5">Analyze document <ArrowRight aria-hidden /></Button>
        </div>
      </section>
      <aside className="min-w-0 border-t border-border pt-6 lg:border-t-0 lg:pt-0">
        <div className="mb-5 flex items-center gap-2 text-xs font-semibold text-muted-foreground"><FileText className="h-4 w-4" aria-hidden /> Demo document</div>
        <div className="document-paper rounded-md border border-border bg-card p-6">
          <div className="mb-5 flex items-center justify-between border-b border-border pb-4"><span className="text-xs font-bold text-foreground">CLINICAL REPORT</span><span className="font-mono text-[10px] text-muted-foreground">01</span></div>
          <div className="space-y-4 text-xs leading-6 text-muted-foreground">
            <p>Patient: <span className="rounded-sm bg-accent px-1 py-0.5 font-medium text-primary">Maria Silva</span><br />Date of birth: <span className="rounded-sm bg-accent px-1 py-0.5 font-medium text-primary">14/03/1985</span></p>
            <p>The patient was seen at the clinic. Reports a history of <span className="rounded-sm bg-destructive/10 px-1 py-0.5 text-destructive">hypertension</span>.</p>
            <div aria-hidden className="space-y-2"><div className="h-1.5 w-full rounded-sm bg-muted" /><div className="h-1.5 w-full rounded-sm bg-muted" /><div className="h-1.5 w-2/3 rounded-sm bg-muted" /></div>
          </div>
          <div className="mt-7 flex items-center gap-2 border-t border-border pt-4 text-[10px] text-muted-foreground"><span className="h-1.5 w-1.5 rounded-full bg-primary" /> Dummy data</div>
        </div>
      </aside>
    </div>
  );
}

/* ---------------- Passo 2: Rever ---------------- */

function CategoryChip({ id }: { id: CategoryId }) {
  const cat = categoryById(id);
  return (
    <span
      className="inline-block rounded-full px-2 py-0.5 text-xs font-medium text-highlight-foreground"
      style={{ backgroundColor: `var(${cat.cssVar})` }}
    >
      {cat.label}
    </span>
  );
}

function confidenceStyle(c: Confidence): string {
  if (c === "certo") return "text-foreground";
  if (c === "provavel") return "text-muted-foreground";
  return "text-destructive";
}

export function ReviewStep({
  analysis,
  decisions,
  onDecision,
  onHideAllCertain,
  onGenerate,
}: {
  analysis: AnalyzeResponse;
  decisions: Record<string, boolean | undefined>;
  onDecision: (id: string, mask: boolean) => void;
  onHideAllCertain: () => void;
  onGenerate: () => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const [catFilter, setCatFilter] = useState<CategoryId | "todas">("todas");
  const [confFilter, setConfFilter] = useState<Confidence | "todas">("todas");

  const uncertain = analysis.items.filter((i) => i.confidence === "incerto");
  const decidedCount = uncertain.filter((i) => decisions[i.id] !== undefined).length;
  const allDecided = decidedCount === uncertain.length;

  const visible = analysis.items.filter(
    (i) =>
      (catFilter === "todas" || i.category === catFilter) &&
      (confFilter === "todas" || i.confidence === confFilter),
  );

  const segments = useMemo(() => {
    const sorted = [...analysis.items].sort((a, b) => a.start - b.start);
    const out: Array<{ text: string; item?: SensitiveItem }> = [];
    let pos = 0;
    for (const item of sorted) {
      if (item.start > pos) out.push({ text: analysis.text.slice(pos, item.start) });
      out.push({ text: analysis.text.slice(item.start, item.end), item });
      pos = item.end;
    }
    if (pos < analysis.text.length) out.push({ text: analysis.text.slice(pos) });
    return out;
  }, [analysis]);

  return (
    <div className="flex flex-col gap-4">
      {uncertain.length > 0 && (
        <section
          aria-label="Precisam da tua decisão"
          className="border-b border-border pb-6"
        >
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-semibold text-foreground">Precisam da tua decisão</h2>
            <span className="text-sm text-muted-foreground">
              {decidedCount} de {uncertain.length} decididos
            </span>
          </div>
          <ul className="flex flex-col gap-2">
            {uncertain.map((item) => {
              const decision = decisions[item.id];
              return (
                <li
                  key={item.id}
                  className="flex flex-wrap items-center gap-3 rounded-lg bg-muted p-3"
                >
                  <span className="min-w-0 flex-1 truncate font-medium text-foreground">
                    {item.text}
                  </span>
                  <CategoryChip id={item.category} />
                  <div className="flex gap-2">
                    <Button variant="ghost"
                      onClick={() => onDecision(item.id, true)}
                      aria-pressed={decision === true}
                      className={`rounded-md px-3 py-1.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-ring ${
                        decision === true
                          ? "bg-primary text-primary-foreground"
                          : "border border-input bg-background text-foreground hover:bg-accent"
                      }`}
                    >
                      Ocultar
                    </Button>
                    <Button variant="ghost"
                      onClick={() => onDecision(item.id, false)}
                      aria-pressed={decision === false}
                      className={`rounded-md px-3 py-1.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-ring ${
                        decision === false
                          ? "bg-primary text-primary-foreground"
                          : "border border-input bg-background text-foreground hover:bg-accent"
                      }`}
                    >
                      Manter
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-muted-foreground">
          Categoria{" "}
          <select
            value={catFilter}
            onChange={(e) => setCatFilter(e.target.value as CategoryId | "todas")}
            className="rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground"
          >
            <option value="todas">Todas</option>
            {CATEGORIES.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label className="text-sm text-muted-foreground">
          Confiança{" "}
          <select
            value={confFilter}
            onChange={(e) => setConfFilter(e.target.value as Confidence | "todas")}
            className="rounded-md border border-input bg-background px-2 py-1.5 text-sm text-foreground"
          >
            <option value="todas">Todas</option>
            {(Object.keys(CONFIDENCE_LABELS) as Confidence[]).map((c) => (
              <option key={c} value={c}>
                {CONFIDENCE_LABELS[c]}
              </option>
            ))}
          </select>
        </label>
        <Button variant="ghost"
          onClick={onHideAllCertain}
          className="ml-auto rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
        >
          Ocultar todos os certos
        </Button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="document-paper max-h-[32rem] overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-card p-4 text-sm leading-relaxed text-foreground">
          {segments.map((seg, i) =>
            seg.item ? (
              <Button variant="ghost"
                key={i}
                onClick={() => setSelected(seg.item?.id ?? null)}
                className={`rounded px-0.5 text-left text-highlight-foreground focus-visible:outline-2 focus-visible:outline-ring ${
                  selected === seg.item.id ? "ring-2 ring-ring" : ""
                }`}
                style={{ backgroundColor: `var(${categoryById(seg.item.category).cssVar})` }}
              >
                {seg.text}
              </Button>
            ) : (
              <span key={i}>{seg.text}</span>
            ),
          )}
        </div>

        <ul className="flex max-h-[32rem] flex-col gap-2 overflow-auto" aria-label="Itens detetados">
          {visible.length === 0 && (
            <li className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
              Nenhum item corresponde aos filtros escolhidos.
            </li>
          )}
          {visible.map((item) => {
            const decision = decisions[item.id];
            return (
              <li key={item.id}>
                <Button variant="ghost"
                  onClick={() => setSelected(item.id)}
                  className={`flex w-full flex-col gap-1.5 rounded-lg border bg-card p-3 text-left hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring ${
                    selected === item.id ? "border-primary" : "border-border"
                  }`}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="min-w-0 flex-1 truncate font-medium text-foreground">
                      {item.text}
                    </span>
                    <CategoryChip id={item.category} />
                  </div>
                  <p className="text-sm text-muted-foreground">{item.reason}</p>
                  <div className="flex items-center justify-between text-xs">
                    <span className={confidenceStyle(item.confidence)}>
                      {CONFIDENCE_LABELS[item.confidence]}
                    </span>
                    <span className="flex items-center gap-1 text-muted-foreground">
                      {decision === false ? (
                        <>
                          <Eye className="h-3.5 w-3.5" aria-hidden /> Manter
                        </>
                      ) : (
                        <>
                          <EyeOff className="h-3.5 w-3.5" aria-hidden /> Ocultar
                        </>
                      )}
                    </span>
                  </div>
                </Button>
              </li>
            );
          })}
        </ul>
      </div>

      <Button variant="ghost"
        onClick={onGenerate}
        disabled={!allDecided}
        className="self-end rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-ring"
      >
        Gerar documento
      </Button>
    </div>
  );
}

/* ---------------- Passo 3: Resultado ---------------- */

export function ResultStep({
  original,
  result,
  onContinue,
}: {
  original: string;
  result: AnonymizeResponse;
  onContinue: () => void;
}) {
  const [sideBySide, setSideBySide] = useState(false);
  const [copied, setCopied] = useState(false);

  const download = () => {
    const blob = new Blob([result.anonymized], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "documento-anonimizado.txt";
    a.click();
    URL.revokeObjectURL(url);
  };

  const copy = async () => {
    await navigator.clipboard.writeText(result.anonymized);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <input
            type="checkbox"
            checked={sideBySide}
            onChange={(e) => setSideBySide(e.target.checked)}
            className="h-4 w-4 accent-[var(--primary)]"
          />
          Vista lado a lado
        </label>
        <div className="ml-auto flex gap-2">
          <Button variant="ghost"
            onClick={copy}
            className="flex items-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
          >
            <Copy className="h-4 w-4" aria-hidden /> {copied ? "Copiado!" : "Copiar"}
          </Button>
          <Button variant="ghost"
            onClick={download}
            className="flex items-center gap-1.5 rounded-md border border-input bg-background px-3 py-1.5 text-sm font-medium text-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
          >
            <Download className="h-4 w-4" aria-hidden /> Descarregar .txt
          </Button>
        </div>
      </div>

      <div className={sideBySide ? "grid gap-4 lg:grid-cols-2" : ""}>
        {sideBySide && (
          <div>
            <h2 className="mb-2 text-sm font-semibold text-muted-foreground">Original</h2>
            <pre className="document-paper max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-card p-4 font-mono text-sm text-foreground">
              {original}
            </pre>
          </div>
        )}
        <div>
          <h2 className="mb-2 text-sm font-semibold text-muted-foreground">Anonimizado</h2>
          <pre className="document-paper max-h-[28rem] overflow-auto whitespace-pre-wrap rounded-lg border border-border bg-card p-4 font-mono text-sm text-foreground">
            {result.anonymized}
          </pre>
        </div>
      </div>

      <Button variant="ghost"
        onClick={onContinue}
        className="self-end rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus-visible:outline-2 focus-visible:outline-ring"
      >
        Ver relatório
      </Button>
    </div>
  );
}

/* ---------------- Passo 4: Relatório ---------------- */

export function ReportStep({
  analysis,
  decisions,
  result,
}: {
  analysis: AnalyzeResponse;
  decisions: Record<string, boolean | undefined>;
  result: AnonymizeResponse;
}) {
  const masked = analysis.items.filter((i) => decisions[i.id]);
  const manualCount = masked.filter((i) => i.confidence !== "certo").length;

  const byCategory = CATEGORIES.map((c) => ({
    cat: c,
    count: masked.filter((i) => i.category === c.id).length,
  })).filter((x) => x.count > 0);
  const maxCount = Math.max(1, ...byCategory.map((x) => x.count));

  const download = () => {
    const blob = new Blob([result.report_md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "relatorio-anonimizacao.md";
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="border-b border-border pb-6">
          <p className="text-3xl font-bold text-foreground">{masked.length}</p>
          <p className="text-sm text-muted-foreground">Itens ocultados</p>
        </div>
        <div className="border-b border-border pb-6">
          <p className="text-3xl font-bold text-foreground">{manualCount}</p>
          <p className="text-sm text-muted-foreground">Decididos manualmente</p>
        </div>
        <div className="border-b border-border pb-6">
          <p className="text-3xl font-bold text-foreground">{byCategory.length}</p>
          <p className="text-sm text-muted-foreground">Categorias afetadas</p>
        </div>
      </div>

      <section aria-label="Itens por categoria" className="border-b border-border pb-6">
        <h2 className="mb-3 font-semibold text-foreground">Por categoria</h2>
        <div className="flex flex-col gap-2">
          {byCategory.map(({ cat, count }) => (
            <div key={cat.id} className="flex items-center gap-3">
              <span className="w-48 truncate text-sm text-muted-foreground">{cat.label}</span>
              <div className="h-4 flex-1 rounded bg-muted">
                <div
                  className="h-4 rounded"
                  style={{
                    width: `${(count / maxCount) * 100}%`,
                    backgroundColor: `var(${cat.cssVar})`,
                  }}
                />
              </div>
              <span className="w-6 text-right text-sm font-medium text-foreground">{count}</span>
            </div>
          ))}
        </div>
      </section>

      <div className="overflow-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-muted-foreground">
              <th className="p-3 font-medium">Texto original</th>
              <th className="p-3 font-medium">Categoria</th>
              <th className="p-3 font-medium">Razão</th>
              <th className="p-3 font-medium">Decisão</th>
            </tr>
          </thead>
          <tbody>
            {masked.map((item) => (
              <tr key={item.id} className="border-b border-border last:border-0">
                <td className="p-3 font-medium text-foreground">{item.text}</td>
                <td className="p-3">
                  <CategoryChip id={item.category} />
                </td>
                <td className="p-3 text-muted-foreground">{item.reason}</td>
                <td className="p-3 text-muted-foreground">
                  {item.confidence === "certo" ? "Automática" : "Manual"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Button variant="ghost"
        onClick={download}
        className="flex items-center gap-1.5 self-end rounded-md bg-primary px-6 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90 focus-visible:outline-2 focus-visible:outline-ring"
      >
        <Download className="h-4 w-4" aria-hidden /> Descarregar relatório (.md)
      </Button>
    </div>
  );
}

export type { Decision };
