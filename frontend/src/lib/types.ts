// Payloads de l'API /api/v1 (miroir de app/api/*.py).

export interface Account {
  id: number;
  code: string;
  label: string;
}

export interface EntryLinePayload {
  account_id: number | null;
  label: string;
  debit_cents: number;
  credit_cents: number;
  project_id?: number | null;
  /** Lot T2 : code de TVA (data/vat_codes.json) et base HT d'une ligne de taxe. */
  vat_code?: string | null;
  vat_base_cents?: number | null;
}

export interface EntryPayload {
  fiscal_year_id: number | null;
  journal_id: number | null;
  entry_date: string;
  description: string;
  lines: EntryLinePayload[];
  bank_transaction_id?: number;
}

export interface EntryResponse {
  id: number;
  reference: string;
  url: string;
  reconciled: boolean;
  editable: boolean;
}

/** Erreurs par champ : fiscal_year_id, entry_date, lines, lines[i].account_id… */
export type FieldErrors = Record<string, string>;

// --- Rapprochement (app/api/reconciliation.py) -----------------------------

export type AttachmentStatus = "ok" | "missing" | "lost" | null;

export type Light = "green" | "orange" | "red";

export interface BankTransaction {
  id: number;
  date: string;
  label: string;
  amount_cents: number;
  reconciled: boolean;
  /** Annulée par la banque après règlement : plus rapprochable. */
  is_reversed: boolean;
  /** Justificatif : null quand la source ne le connaît pas (OFX). */
  attachment_status: AttachmentStatus;
  category: string | null;
  /** Feu (lot TX1) : couleur et motifs ; catégorie affichée (Lyvre d'abord, sinon Qonto). */
  light?: Light;
  light_reasons?: string[];
  category_display?: { label: string; source: "lyvre" | "qonto" } | null;
  raw_type?: string | null;
  entity: string | null;
  entry: { id: number; reference: string; url: string } | null;
  new_entry_url: string;
  /** Débit Qonto avec justificatif, sans facture : facture d'achat à créer depuis la pièce. */
  purchase_from_attachment?: boolean;
}

export interface Counters {
  unreconciled: number;
  total: number;
}

export interface Suggestion {
  journal_line_id: number;
  entry_id: number;
  reference: string;
  entry_date: string;
  label: string;
  account_code: string;
  amount_cents: number;
  /** 2 = même date, 1 = date proche */
  score: number;
}

export interface UndoRequest {
  method: "POST";
  url: string;
  body: unknown;
}

export interface ItemResult {
  bank_transaction_id: number;
  status: "ok" | "error" | "found";
  message?: string;
}

export interface BatchResponse {
  results: ItemResult[];
  counters: Counters | null;
  undo: UndoRequest | null;
}

export interface ApplyRulesResponse {
  summary: { matched: number; posted: number; skipped: number; total: number };
  errors: string[];
  counters: Counters | null;
  undo: UndoRequest | null;
}
