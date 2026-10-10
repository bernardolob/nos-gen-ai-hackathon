import type { AnalyzeResponse, CategoryId, Confidence, SensitiveItem } from "./types";

type Seed = { t: string; item?: { category: CategoryId; reason: string; confidence: Confidence } };

// The document is assembled from segments so that start/end offsets are
// always exact — never hand-maintained character positions.
const SEGMENTS: Seed[] = [
  { t: "RELATÓRIO CLÍNICO\n\nUtente: " },
  {
    t: "Maria Conceição Oliveira Santos",
    item: { category: "identificacao", reason: "Nome completo da utente", confidence: "certo" },
  },
  { t: ", nascida a " },
  {
    t: "12 de março de 1968",
    item: { category: "quasi", reason: "Data de nascimento completa", confidence: "certo" },
  },
  { t: ", residente na " },
  {
    t: "Rua das Flores 24, 3.º esquerdo",
    item: { category: "identificacao", reason: "Morada completa da utente", confidence: "certo" },
  },
  { t: ", " },
  {
    t: "4000-189 Porto",
    item: {
      category: "quasi",
      reason: "Código postal pode ajudar a localizar a utente",
      confidence: "incerto",
    },
  },
  { t: ". Contacto: " },
  {
    t: "912 345 678",
    item: { category: "identificacao", reason: "Número de telemóvel pessoal", confidence: "certo" },
  },
  { t: ". Cartão de cidadão " },
  {
    t: "12345678",
    item: {
      category: "identificacao",
      reason: "Número de documento de identificação",
      confidence: "certo",
    },
  },
  { t: ", NIF " },
  {
    t: "245 789 123",
    item: { category: "financeiros", reason: "Número de identificação fiscal", confidence: "provavel" },
  },
  { t: ".\n\nA utente, " },
  {
    t: "casada e mãe de dois filhos",
    item: { category: "familia", reason: "Informação sobre a vida familiar", confidence: "provavel" },
  },
  { t: ", foi observada em consulta no dia 3 de outubro de 2026. Refere diagnóstico prévio de " },
  {
    t: "diabetes tipo 2",
    item: { category: "saude", reason: "Diagnóstico médico da utente", confidence: "certo" },
  },
  { t: " e " },
  {
    t: "hipertensão arterial",
    item: { category: "saude", reason: "Condição de saúde da utente", confidence: "certo" },
  },
  { t: ". O teste genético realizado em 2024 identificou " },
  {
    t: "mutação BRCA1",
    item: { category: "geneticos", reason: "Resultado de teste genético", confidence: "certo" },
  },
  { t: ". A " },
  {
    t: "impressão digital",
    item: { category: "biometricos", reason: "Dado biométrico registado no hospital", confidence: "certo" },
  },
  { t: " da utente foi registada no sistema de acesso do hospital.\n\nA utente, de " },
  {
    t: "religião católica",
    item: { category: "origem", reason: "Convicção religiosa da utente", confidence: "certo" },
  },
  { t: " e " },
  {
    t: "militante do Partido Socialista",
    item: { category: "origem", reason: "Afiliação política da utente", confidence: "certo" },
  },
  { t: ", mencionou " },
  {
    t: "consumo ocasional de álcool",
    item: {
      category: "comportamentos",
      reason: "Hábito pessoal que pode ser sensível",
      confidence: "incerto",
    },
  },
  { t: ". O pagamento da consulta foi feito a partir da conta " },
  {
    t: "PT50 0002 0123 1234 5678 9015 4",
    item: { category: "financeiros", reason: "IBAN da conta bancária da utente", confidence: "certo" },
  },
  { t: ".\n\nObservações: mulher, 58 anos, profissão " },
  {
    t: "professora",
    item: {
      category: "quasi",
      reason: "Profissão pode contribuir para reidentificação",
      confidence: "incerto",
    },
  },
  { t: ".\n\nAssinado: " },
  {
    t: "Dr. João Pedro Almeida",
    item: {
      category: "identificacao",
      reason: "Nome do médico assistente, não da utente",
      confidence: "incerto",
    },
  },
  { t: ", cédula 45678." },
];

export function buildMockAnalysis(): AnalyzeResponse {
  let text = "";
  const items: SensitiveItem[] = [];
  let nextId = 1;
  for (const seg of SEGMENTS) {
    const start = text.length;
    text += seg.t;
    if (seg.item) {
      items.push({
        id: String(nextId++),
        text: seg.t,
        start,
        end: text.length,
        category: seg.item.category,
        reason: seg.item.reason,
        confidence: seg.item.confidence,
      });
    }
  }
  return { text, items };
}
