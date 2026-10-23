// Ventes (lot S1) : factures et avoirs de l'application (API /api/v1/sales).
import type { Tone } from "../../components/StatusBadge";
import type { Option } from "../purchases/types";

export const SALES_KEY = ["sales"];
export const BILLING_KEY = ["billing-settings"];

export type SaleKind = "invoice" | "credit_note";
export type SaleStatus = "draft" | "issued" | "partially_paid" | "paid" | "canceled";

export interface SaleRow {
  id: number; kind: SaleKind; kind_label: string; status: SaleStatus; status_label: string; number: string | null;
  source: "app" | "qonto"; client: { id: number; name: string }; issue_date: string | null; due_date: string | null;
  untaxed_cents: number; tax_cents: number; total_cents: number; paid_cents: number; sent_at: string | null; overdue: boolean;
  due_cents: number; reminder_count: number; last_reminder_at: string | null;
}

export interface SalePayment {
  id: number; amount_cents: number; paid_on: string; origin: "bank" | "manual"; method: string; vat_released_cents: number;
  account: string | null; transaction: { id: number; label: string | null } | null; journal_entry: { id: number; reference: string } | null;
}

export interface PaymentOptions {
  due_cents: number;
  candidates: { id: number; date: string; label: string; amount_cents: number; account: string; same_client: boolean; exact: boolean; rule: boolean }[];
  accounts: { value: string; label: string; kind: "bank" | "cash" }[];
  methods: { value: string; label: string }[];
}

export interface SaleLineRow {
  product_id: string; label: string; description: string; quantity: string; unit: string; unit_price: string;
  discount: string; vat_rate: string; account_code: string; project_id: string; nature: "goods" | "services";
}

export interface SaleDetail extends Omit<SaleRow, "client"> {
  client: { id: number; name: string; address_line1: string | null; address_line2: string | null; postal_code: string | null;
    city: string | null; country: string | null; siren: string | null; vat_number: string | null; email: string | null };
  service_start: string | null; service_end: string | null; operation_type: string; purchase_order: string; terms: string;
  header: string; footer: string; vat_mode: "none" | "receipts" | "debits" | null; credit_reason: string | null;
  lines: (SaleLineRow & { id: number; untaxed_cents: number; vat_cents: number; total_cents: number })[];
  vat_rows: { rate: number; base: number; tax: number }[];
  journal_entry: { id: number; reference: string } | null; invoice: { id: number; number: string } | null;
  credit_notes: { id: number; number: string | null; status: SaleStatus; total_cents: number }[];
  remaining_credit_cents: number; issue_problems: string[]; recipients: string[];
  emails: { sent_at: string; recipients: string; subject: string | null; status: "sent" | "failed"; error: string | null;
    purpose: "send" | "reminder" }[];
  payments: SalePayment[];
  pdf_url: string;
}

export interface SaleProductOption extends Option {
  account: string; rate: string; price: string; unit: string; description: string; nature: "goods" | "services";
}

export interface SaleFormOptions {
  clients: Option[]; products: SaleProductOption[]; sale_accounts: Option[]; default_account: string;
  projects: Option[]; units: string[]; operation_types: Option[]; vat_mode: "none" | "receipts" | "debits";
  vat_liable: boolean; payment_terms_days: number;
}

export const STATUS_TONES: Record<SaleStatus, Tone> = {
  draft: "todo", issued: "info", partially_paid: "info", paid: "ok", canceled: "neutral",
};

export const VAT_MODE_LABELS: Record<string, string> = {
  none: "Non assujetti : TVA non applicable (art. 293 B du CGI)",
  receipts: "TVA des prestations exigible à l'encaissement",
  debits: "TVA exigible d'après les débits",
};

export const EMPTY_SALE_LINE: SaleLineRow = {
  product_id: "", label: "", description: "", quantity: "1", unit: "", unit_price: "", discount: "", vat_rate: "",
  account_code: "", project_id: "", nature: "services",
};

const num = (text: string) => {
  const value = Number((text || "").replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(value) ? value : 0;
};

/** HT estimé d'une ligne en centimes (le serveur fait foi : TVA arrondie par taux). */
export function lineUntaxed(row: SaleLineRow): number {
  return Math.round(num(row.quantity || "1") * num(row.unit_price) * 100 * (1 - num(row.discount) / 100));
}

/** Totaux estimés : HT, TVA par taux, TTC (même règle que le serveur). */
export function estimate(rows: SaleLineRow[], exempt: boolean): { untaxed: number; tax: number; total: number } {
  const byRate = new Map<number, number>();
  let untaxed = 0;
  for (const row of rows) {
    if (!row.label && !row.unit_price) continue;
    const base = lineUntaxed(row);
    untaxed += base;
    const rate = exempt ? 0 : num(row.vat_rate);
    byRate.set(rate, (byRate.get(rate) ?? 0) + base);
  }
  let tax = 0;
  for (const [rate, base] of byRate) tax += Math.round((base * rate) / 100);
  return { untaxed, tax, total: untaxed + tax };
}

/** Ligne remplie depuis un produit du catalogue (libellé, prix, TVA, compte, unité, nature). */
export function fromProduct(row: SaleLineRow, product: SaleProductOption | undefined, fallbackAccount: string): SaleLineRow {
  if (!product) return { ...row, product_id: "" };
  return { ...row, product_id: product.value, label: product.label, description: product.description || row.description,
    unit_price: product.price || row.unit_price, vat_rate: product.rate || row.vat_rate,
    account_code: product.account || row.account_code || fallbackAccount, unit: product.unit || row.unit, nature: product.nature };
}
