export interface BankAccount {
  id: number; label: string; iban: string | null;
  account: { id: number; code: string; label: string };
  qonto: { account_id: string; sync_from: string | null; synced_at: string | null } | null;
  transactions?: number; unreconciled?: number;
}

export interface Option { value: string; label: string }

export const BANK_ACCOUNTS_KEY = ["bank-accounts"];
