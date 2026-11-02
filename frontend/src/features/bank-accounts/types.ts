export interface BankAccount {
  id: number; label: string; iban: string | null; kind: "bank" | "cash"; balance_cents?: number;
  account: { id: number; code: string; label: string };
  qonto: { account_id: string; sync_from: string | null; synced_at: string | null } | null;
  transactions?: number; unreconciled?: number;
  /** Solde bancaire (comptes bancaires) : solde d'ouverture + transactions, ou somme de l'exercice s'il manque. */
  bank_balance?: { balance_cents: number; at: string; opening_missing: boolean; fiscal_year: string | null };
}

export interface OpeningBalance {
  amount_cents: number | null; date: string | null; proposed_date: string | null;
  entry: { id: number; reference: string; counterpart: string | null } | null;
  entry_allowed: boolean;
}

export interface Option { value: string; label: string }

export const BANK_ACCOUNTS_KEY = ["bank-accounts"];
