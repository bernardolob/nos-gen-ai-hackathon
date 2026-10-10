import { buildMockAnalysis } from "./mock-data";
import type { AnalyzeResponse, AnonymizeResponse, Decision, SensitiveItem } from "./types";

/**
 * Service layer for the external anonymization backend.
 * Mock mode is ON by default: it is only disabled when VITE_API_URL is set.
 */
const API_URL = (import.meta.env["VITE_API_URL"] as string | undefined)?.replace(/\/+$/, "");
export const isMockMode = !API_URL;

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export async function analyzeDocument(
  file: File,
  onStatus?: (message: string) => void,
): Promise<AnalyzeResponse> {
  if (isMockMode) {
    onStatus?.("A extrair texto...");
    await wait(900);
    onStatus?.("A detetar dados sensíveis...");
    await wait(1100);
    onStatus?.("A verificar...");
    await wait(700);
    return buildMockAnalysis();
  }
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_URL}/analyze`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`O backend respondeu com o erro ${res.status}.`);
  return (await res.json()) as AnalyzeResponse;
}

function maskText(text: string, items: SensitiveItem[], decisions: Decision[]): string {
  const maskIds = new Set(decisions.filter((d) => d.mask).map((d) => d.id));
  const toMask = items.filter((i) => maskIds.has(i.id)).sort((a, b) => b.start - a.start);
  let out = text;
  for (const item of toMask) {
    out = out.slice(0, item.start) + "*".repeat(item.end - item.start) + out.slice(item.end);
  }
  return out;
}

function buildMockReport(items: SensitiveItem[], decisions: Decision[]): string {
  const decisionById = new Map(decisions.map((d) => [d.id, d.mask]));
  const masked = items.filter((i) => decisionById.get(i.id));
  const lines = [
    "# Relatório de anonimização",
    "",
    `Total de itens ocultados: ${masked.length}`,
    "",
    "| Texto original | Categoria | Razão | Decisão |",
    "| --- | --- | --- | --- |",
    ...masked.map(
      (i) =>
        `| ${i.text} | ${i.category} | ${i.reason} | ${i.confidence === "certo" ? "automática" : "manual"} |`,
    ),
  ];
  return lines.join("\n");
}

export async function anonymizeDocument(
  text: string,
  items: SensitiveItem[],
  decisions: Decision[],
): Promise<AnonymizeResponse> {
  if (isMockMode) {
    await wait(800);
    return { anonymized: maskText(text, items, decisions), report_md: buildMockReport(items, decisions) };
  }
  const res = await fetch(`${API_URL}/anonymize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, decisions }),
  });
  if (!res.ok) throw new Error(`O backend respondeu com o erro ${res.status}.`);
  return (await res.json()) as AnonymizeResponse;
}
