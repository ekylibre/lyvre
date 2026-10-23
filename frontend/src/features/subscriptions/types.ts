// Achats › Abonnements (lot S6) : contrats récurrents et échéances attendues.
import type { Tone } from "../../components/StatusBadge";
import type { Option } from "../purchases/types";

export const SUBSCRIPTIONS_KEY = ["subscriptions"];

export type PeriodStatus = "expected" | "invoiced" | "paid" | "missing" | "skipped";

export interface Period {
  id: number; due_date: string; expected_cents: number; status: PeriodStatus; status_label: string;
  purchase: { id: number; number: string | null; total_cents: number; issue_date: string | null } | null;
  transaction: { id: number; label: string | null; amount_cents: number; date: string } | null;
}

export interface Subscription {
  id: number; label: string; category: string; category_label: string; supplier: { id: number; name: string };
  amount_cents: number; amount_fixed: boolean; frequency: "monthly" | "quarterly" | "yearly"; frequency_label: string;
  due_day: number; monthly_cents: number; start_date: string; end_date: string | null; renewal_date: string | null;
  notice_days: number | null; next_renewal: string | null; notice_deadline: string | null; notice_alert: boolean;
  active: boolean; notes: string; product_id: string; bank_account_id: string; last_period: Period | null; missing: number;
  periods?: Period[];
}

export interface SubscriptionsMeta {
  summary: { monthly_cents: number; yearly_cents: number; by_category: { category: string; label: string; monthly_cents: number }[];
    missing: number; notice_alerts: number };
  categories: Option[]; frequencies: Option[]; suppliers: Option[]; products: Option[]; bank_accounts: Option[];
}

export const PERIOD_TONES: Record<PeriodStatus, Tone> = {
  expected: "info", invoiced: "info", paid: "ok", missing: "gap", skipped: "neutral",
};
