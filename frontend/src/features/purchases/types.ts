// Factures d'achat : types de l'API /api/v1/purchases et libellés partagés par les écrans.
import type { IntegrationState } from "../../components/IntegrationNotice";
import type { Job } from "../../components/JobStatus";
import type { MonthOption } from "../../components/MonthSelect";
import type { Tone } from "../../components/StatusBadge";

export const PURCHASES_KEY = ["purchases"];

export interface Option { value: string; label: string }

export interface PurchaseState { code: "posted" | "ready" | "to_complete" | "hidden"; label: string; reasons: string[] }

export interface Purchase {
  id: number; source: "qonto" | "manual"; invoice_number: string | null; issue_date: string | null; due_date: string | null;
  is_credit_note: boolean; is_einvoice: boolean; is_hidden: boolean; total_cents: number;
  supplier: { id: number; name: string } | null; supplier_name: string | null;
  qonto_status: string | null; qonto_status_label: string | null; review_reason: string | null; has_attachment: boolean;
  qonto_upload_status: "sent" | "failed" | null; qonto_upload_error: string | null; in_qonto: boolean;
  state: PurchaseState; journal_entry_id: number | null;
}

/** Confirmation de suppression : écriture supprimée aussi ; facture présente dans Qonto (reçue de Qonto ou
 * déposée depuis la saisie), que la synchronisation réimporte si elle y est modifiée. */
export function deleteMessage(p: Pick<Purchase, "journal_entry_id" | "in_qonto" | "source">): string | undefined {
  const qonto = p.source === "manual" ? "Elle a été déposée dans Qonto et y reste" : "Elle reste dans Qonto";
  return [p.journal_entry_id && "Son écriture d'achat sera supprimée aussi.",
    p.in_qonto && `${qonto} : supprimez-la aussi dans Qonto si vous ne voulez pas la voir revenir : la synchronisation la réimporte dès qu'elle y est modifiée.`]
    .filter(Boolean).join(" ") || undefined;
}

export interface QontoState extends IntegrationState { upload: boolean }

export interface PurchasesMeta {
  counters: { to_complete: number; to_review: number; to_replace: number; supplier_proposals: number; hidden: number;
    without_supplier: number; ready: number };
  suppliers: Option[]; states: Option[]; statuses: Option[]; months: MonthOption[];
  sync: { from: string; synced_at: string | null; job: Job | null };
  qonto: QontoState;
}

/** Ligne de saisie : champs texte, comme le formulaire (montants « 33,33 »). */
export interface LineRow {
  product_id: string; account_code: string; label: string; untaxed: string; vat_rate: string; vat: string; project_id?: string;
}

export interface ProductOption extends Option { account: string; rate: string }

export interface FormOptions { products: ProductOption[]; charge_accounts: Option[]; qonto: QontoState; projects?: Option[] }

export interface Payment {
  id: number; origin: "qonto" | "match" | "manual" | "associate"; status: "to_import" | "settled" | "reversed" | "other_entry" | "pending";
  status_label: string; qonto_transaction_id: string | null;
  /** Règlement par le compte courant d'un associé (module « Associés »). */
  associate?: { id: number; name: string }; date?: string | null; amount_cents?: number;
  transaction: { id: number; date: string; label: string; amount_cents: number; bank_account: string; bank_account_id: number } | null;
  entry: { reference: string; url: string } | null;
}

export interface PurchaseDetail {
  item: Purchase & {
    payment_date: string | null; untaxed_cents: number | null; tax_cents: number | null;
    supplier_vat: string | null; supplier_siret: string | null; supplier_iban: string | null; supplier_account_code: string | null;
    attachment: { name: string; size: number | null; mime: string; url: string } | null;
    entry: { reference: string; date: string; url: string } | null;
  };
  fiscal_year: { label: string; vat_liable: boolean } | null;
  lines: LineRow[];
  lines_view: { product: string | null; account: string | null; label: string; untaxed_cents: number; vat_rate: string | null;
    project?: string | null;
    vat_cents: number; total_cents: number }[];
  payments: Payment[];
  awaiting_payment: boolean;
  suggestions: { id: number; date: string; bank_account: string; label: string; amount_cents: number; rule: boolean }[];
  match_window: [string, string] | null;
  can_send: boolean;
  /** Module « Associés » actif : règlement par un associé possible si `blocker` est nul. */
  associate_payment: { blocker: string | null; associates: Option[] } | null;
  meta: FormOptions;
}

export const STATE_TONES: Record<PurchaseState["code"], Tone> = { posted: "ok", ready: "info", to_complete: "todo", hidden: "neutral" };

export const PAYMENT_TONES: Record<Payment["status"], Tone> = {
  settled: "ok", pending: "todo", other_entry: "gap", reversed: "gap", to_import: "neutral",
};

export function kind(p: Pick<Purchase, "is_credit_note">): string {
  return p.is_credit_note ? "Avoir" : "Facture";
}

export function purchaseTitle(p: Pick<Purchase, "is_credit_note" | "invoice_number">): string {
  return `${kind(p)} ${p.invoice_number || "sans numéro"}`;
}
