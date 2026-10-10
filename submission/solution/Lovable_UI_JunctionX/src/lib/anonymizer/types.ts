export type Confidence = "certo" | "provavel" | "incerto";

export type CategoryId =
  | "identificacao"
  | "saude"
  | "geneticos"
  | "biometricos"
  | "origem"
  | "financeiros"
  | "familia"
  | "comportamentos"
  | "quasi";

export interface Category {
  id: CategoryId;
  label: string;
  /** CSS variable holding the accessible category color. */
  cssVar: string;
}

export const CATEGORIES: Category[] = [
  { id: "identificacao", label: "Identificação pessoal", cssVar: "--cat-identificacao" },
  { id: "saude", label: "Saúde", cssVar: "--cat-saude" },
  { id: "geneticos", label: "Genéticos", cssVar: "--cat-geneticos" },
  { id: "biometricos", label: "Biométricos", cssVar: "--cat-biometricos" },
  {
    id: "origem",
    label: "Origem étnica / religião / política / orientação sexual",
    cssVar: "--cat-origem",
  },
  { id: "financeiros", label: "Financeiros", cssVar: "--cat-financeiros" },
  { id: "familia", label: "Vida familiar", cssVar: "--cat-familia" },
  { id: "comportamentos", label: "Comportamentos pessoais", cssVar: "--cat-comportamentos" },
  { id: "quasi", label: "Quasi-identificadores", cssVar: "--cat-quasi" },
];

export const categoryById = (id: CategoryId): Category =>
  CATEGORIES.find((c) => c.id === id) ?? CATEGORIES[0]!;

export interface SensitiveItem {
  id: string;
  text: string;
  start: number;
  end: number;
  category: CategoryId;
  reason: string;
  confidence: Confidence;
}

export interface AnalyzeResponse {
  text: string;
  items: SensitiveItem[];
}

export interface Decision {
  id: string;
  mask: boolean;
}

export interface AnonymizeResponse {
  anonymized: string;
  report_md: string;
}

export const CONFIDENCE_LABELS: Record<Confidence, string> = {
  certo: "Certo",
  provavel: "Provável",
  incerto: "Incerto",
};
