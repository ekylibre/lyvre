// Déclarations de TVA (lot T3) : miroir de app/api/vat_returns.py.
import type { Tone } from "../../components/StatusBadge";

export const VAT_RETURNS_KEY = ["vat-returns"];

export type PeriodStatus = "to_prepare" | "in_progress" | "validated" | "declared";

export interface VatReturnInfo {
  refund_cents: number; form?: string;
  id: number; status: "validated" | "declared"; status_label: string; due_cents: number; credit_cents: number;
  credit_carried_cents: number; declared_on: string | null; declared_reference: string | null; validated_at: string | null;
  liquidation_entry: { id: number; reference: string } | null;
}

export interface PeriodRow {
  period: string; start: string; end: string; deadline: string; late: boolean; status: PeriodStatus; status_label: string;
  return: VatReturnInfo | null;
}

export interface VatReturnsList {
  items: PeriodRow[]; fiscal_year: { id: number; label: string; vat_period?: string | null } | null; fiscal_years: { value: string; label: string }[];
  setup?: { message: string; link: string; link_label: string } | null;
}

/** Ligne du formulaire : section, case (base HT pour les lignes de taux) ou total ; montants en euros. */
export interface FormRow {
  kind: "section" | "box" | "total"; label: string; line?: string; code?: string | null; with_base?: boolean;
  base?: number | null; amount?: number;
  /** Mention sous la ligne (TVA autoliquidée : due d'un côté, déduite de l'autre). */
  note?: string;
}

export interface Check { level: "error" | "warning"; message: string; count: number | null }

export interface VatReturnPreview {
  period: string; rows: FormRow[]; codes: Record<string, { base: number; tax: number; deductible: number }>;
  checks: Check[]; deadline: string; form_year: number; credit_carried_cents: number; due_cents: number;
  credit_cents: number; lines_count?: number; vat_return: VatReturnInfo | null;
  /** Lot AG2.a : remboursement de crédit possible (3519), en centimes. */
  refund?: { minimum_cents: number; maximum_cents: number; possible: boolean } | null;
  /** Lot AG2.b : formulaire (3310-CA3-SD, 3517-AGR-SD), code (CA3, CA12A), acomptes imputés (ligne 25). */
  form?: string; form_code?: string; label?: string; installments_cents?: number | null;
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
  if (period.toUpperCase().endsWith("-A")) {  // CA12A : année civile « 2026-A », exercice « 2025-07-A » (CA12AE)
    const parts = period.split("-");
    if (parts.length === 2) return `année ${parts[0]}`;
    const start = new Date(Number(parts[0]), Number(parts[1]) - 1, 1);
    return `exercice ouvert en ${start.toLocaleDateString("fr-FR", { month: "long", year: "numeric" })}`;
  }
  const [year, part] = period.split("-");
  if (part?.toUpperCase().startsWith("T")) return `${part.slice(1) === "1" ? "1er" : `${part.slice(1)}e`} trimestre ${year}`;
  return new Date(Number(year), Number(part) - 1, 1).toLocaleDateString("fr-FR", { month: "long", year: "numeric" });
}

/** Montant en euros entiers (cases du formulaire), espaces fines. */
export function formatWholeEuros(euros: number | null | undefined): string {
  if (euros == null) return "";
  return `${euros < 0 ? "−" : ""}${Math.abs(euros).toLocaleString("fr-FR")} €`;
}

/** Lot AG2.c : acomptes du RSA (3525 bis), miroir de `GET /vat-returns/installments`. */
export type InstallmentStatus = "to_prepare" | "dispensed" | "validated" | "declared";

export interface InstallmentRow {
  number: number; label: string; start: string; end: string; deadline: string; status: InstallmentStatus;
  status_label: string; late: boolean; amount_cents: number | null; motive: string | null; can_validate: boolean;
  return: VatReturnInfo | null;
}

export interface InstallmentSchedule {
  period: string; label: string; start: string; end: string; dispensed: boolean; proposed_cents: number | null;
  planned_cents: number; exemption_cents: number; share_bp: number;
  reference: { source: "ca12a" | "entered" | "missing"; due_cents: number | null; assets_cents: number | null;
    before_assets_cents: number | null; label: string | null };
  estimate: { to_date_cents: number; until: string; year_cents: number } | null;
  annual_return: VatReturnInfo | null; warnings: string[]; items: InstallmentRow[];
}

export const INSTALLMENT_TONES: Record<InstallmentStatus, Tone> = {
  to_prepare: "todo", dispensed: "neutral", validated: "info", declared: "ok",
};

/** Lot AG2.d : livres de TVA, miroir de `GET /vat-books/sales` et `/vat-books/purchases`. */
export interface SalesBook {
  start: string; end: string;
  items: { date: string; entry_id: number; reference: string | null; label: string; entity: string; code: string;
    code_label: string; line: string | null; category: string; base_cents: number; tax_cents: number }[];
  totals: { line: string | null; category: string; base_cents: number; tax_cents: number }[];
  total: { base_cents: number; tax_cents: number };
  control: { form: string; validated: boolean; ok: boolean; lines: { line: string; label: string; book_base: number;
    book_tax: number; return_base: number; return_tax: number; ok: boolean }[] } | null;
}

export interface PurchasesBook {
  start: string; end: string;
  items: { date: string; entry_id: number; reference: string | null; label: string; entity: string;
    group: "assets" | "other"; group_label: string; codes: string[]; ht_cents: number; deductible_cents: number;
    reverse_charge_cents: number; non_deductible: boolean }[];
  totals: { group: "assets" | "other"; label: string; ht_cents: number; deductible_cents: number;
    reverse_charge_cents: number; non_deductible_ht_cents: number }[];
  control: { form: string; validated: boolean; ok: boolean; book_assets: number; book_other: number; book_total: number;
    return_17: number; return_18: number; return_14: number; return_total: number } | null;
}
