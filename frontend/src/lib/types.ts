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
