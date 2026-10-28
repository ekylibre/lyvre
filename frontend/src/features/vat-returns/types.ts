// Déclarations de TVA (lot T3) : miroir de app/api/vat_returns.py.
import type { Tone } from "../../components/StatusBadge";

export const VAT_RETURNS_KEY = ["vat-returns"];

export type PeriodStatus = "to_prepare" | "in_progress" | "validated" | "declared";

export interface VatReturnInfo {
  id: number; status: "validated" | "declared"; status_label: string; due_cents: number; credit_cents: number;
  credit_carried_cents: number; declared_on: string | null; declared_reference: string | null; validated_at: string | null;
  liquidation_entry: { id: number; reference: string } | null;
}

export interface PeriodRow {
  period: string; start: string; end: string; deadline: string; late: boolean; status: PeriodStatus; status_label: string;
  return: VatReturnInfo | null;
}

export interface VatReturnsList {
  items: PeriodRow[]; fiscal_year: { id: number; label: string } | null; fiscal_years: { value: string; label: string }[];
}

/** Ligne du formulaire : section, case (base HT pour les lignes de taux) ou total ; montants en euros. */
export interface FormRow {
  kind: "section" | "box" | "total"; label: string; line?: string; code?: string | null; with_base?: boolean;
  base?: number | null; amount?: number;
}

export interface Check { level: "error" | "warning"; message: string; count: number | null }

export interface VatReturnPreview {
  period: string; rows: FormRow[]; codes: Record<string, { base: number; tax: number; deductible: number }>;
  checks: Check[]; deadline: string; form_year: number; credit_carried_cents: number; due_cents: number;
  credit_cents: number; lines_count?: number; vat_return: VatReturnInfo | null;
}

export interface BoxLine {
  id: number; entry_id: number; reference: string | null; date: string; description: string; account: string;
  label: string; debit_cents: number; credit_cents: number; vat_code: string | null; vat_base_cents: number | null;
}

export const STATUS_TONES: Record<PeriodStatus, Tone> = {
  to_prepare: "todo", in_progress: "neutral", validated: "info", declared: "ok",
};

/** « 2026-07 » → « juillet 2026 ». */
export function monthLabel(period: string): string {
  const [year, month] = period.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
}

/** Montant en euros entiers (cases du formulaire), espaces fines. */
export function formatWholeEuros(euros: number | null | undefined): string {
  if (euros == null) return "";
  return `${euros < 0 ? "−" : ""}${Math.abs(euros).toLocaleString("fr-FR")} €`;
}
