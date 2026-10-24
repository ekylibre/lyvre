// Immobilisations (lot F5).
export const ASSETS_KEY = ["assets"];

export interface Option { value: string; label: string }
export interface ScheduleRow {
  fiscal_year_id: number | null; label: string; start: string; stop: string; days: number;
  amount_cents: number; cumulative_cents: number; net_cents: number; posted: boolean;
}
export interface AssetItem {
  id: number; parent_id: number | null; label: string; account: { id: number; code: string; label: string };
  depreciation_account_code: string | null; acquired_on: string; in_service_date: string | null;
  acquisition_cents: number; residual_cents: number; method: "linear" | "regressive" | "none"; method_label: string;
  duration_months: number | null; fiscal_coefficient: string | null; prior_depreciation_cents: number; prior_as_of: string | null;
  project_id: number | null; project: string | null; status: string; status_label: string;
  accumulated_cents: number; net_cents: number; disposal_date: string | null; disposal_price_cents: number | null;
  purchase_line_id: number | null; notes: string; components: AssetItem[]; deletable: boolean; schedule?: ScheduleRow[];
}
export interface AssetsMeta { accounts: Option[]; methods: Option[]; statuses: Option[]; enabled: boolean }

export const STATUS_TONES: Record<string, "ok" | "todo" | "gap" | "info" | "neutral"> = {
  waiting: "todo", in_use: "ok", depreciated: "info", sold: "neutral", scrapped: "neutral",
};
