export interface HistoryEntry {
  attempt: number;
  text: string;
  reason: string;
}

export interface Snapshot {
  has_document: boolean;
  attempt: number;
  text: string;
  approved: boolean;
  history: HistoryEntry[];
  mode: "model" | "rules";
  warnings: number;
  issues: number;
}

export const EMPTY_SNAPSHOT: Snapshot = {
  has_document: false,
  attempt: 0,
  text: "",
  approved: false,
  history: [],
  mode: "model",
  warnings: 0,
  issues: 0,
};

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const MAX_REASON_CHARS = 2000;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
