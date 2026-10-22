// Odoo : commandes du point de vente, factures clients, import de lignes par lots.
import type { IntegrationState } from "../../components/IntegrationNotice";
import type { MonthOption } from "../../components/MonthSelect";
import type { Tone } from "../../components/StatusBadge";

export const ORDERS_KEY = ["orders"];
export const INVOICES_KEY = ["customer-invoices"];
export const ODOO_IMPORTS_KEY = ["odoo-imports"];

export interface Option { value: string; label: string }

export interface OdooMeta { months: MonthOption[]; odoo: IntegrationState; limit: number }

export const ORDER_TONES: Record<string, Tone> = { done: "ok", invoiced: "ok", paid: "info", cancel: "gap" };
export const INVOICE_TONES: Record<string, Tone> = { posted: "ok", cancel: "gap" };
export const PAYMENT_TONES: Record<string, Tone> = {
  paid: "ok", partial: "todo", in_payment: "info", reversed: "neutral", not_paid: "gap",
};

/** Synchronisation Odoo synchrone : quelques secondes, résultat en notification. */
export const SYNC_HINT = "La synchronisation peut prendre quelques secondes.";

export function quantity(qty: number): string {
  return Number.isInteger(qty) ? String(qty) : qty.toLocaleString("fr-FR");
}
