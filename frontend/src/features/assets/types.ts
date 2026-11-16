// Immobilisations (lot F5).
export const ASSETS_KEY = ["assets"];

export interface Option { value: string; label: string }
export interface ScheduleRow {
  fiscal_year_id: number | null; label: string; start: string; stop: string; days: number;
  amount_cents: number; cumulative_cents: number; net_cents: number; posted: boolean;
}
export interface AssetItem {
  /** Lot AG8.c : activité de la fiche (analytique agricole). */
  activity_id?: number | null; activity?: string | null;
  id: number; parent_id: number | null; label: string; account: { id: number; code: string; label: string };
  depreciation_account_code: string | null; acquired_on: string; in_service_date: string | null;
  acquisition_cents: number; residual_cents: number; method: "linear" | "regressive" | "none"; method_label: string;
  duration_months: number | null; full_first_year?: boolean; fiscal_coefficient: string | null; prior_depreciation_cents: number; prior_as_of: string | null;
  project_id: number | null; project: string | null; status: string; status_label: string;
  accumulated_cents: number; net_cents: number; disposal_date: string | null; disposal_price_cents: number | null;
  purchase_line_id: number | null; notes: string; components: AssetItem[]; deletable: boolean; schedule?: ScheduleRow[];
  /** Bien vivant immobilisé (lot AG5.a), comptes 24x / 234x. */
  living?: { kind: string; species: string | null; age_class: string | null; units: number | null; origin: string | null } | null;
}
export interface AssetsMeta { accounts: Option[]; methods: Option[]; statuses: Option[]; enabled: boolean;
  living_kinds?: Option[]; living_origins?: Option[]; plantation_references?: PlantationReferences }
type OrchardRow = [string | null, string | null, string | null] | null;
export interface PlantationReferences {
  vine_years: number | null; vine_source: string | null;
  orchards: { conducts: Record<string, string>; columns: string[]; source: string; source_label: string; note: string;
    species: ({ key: string; label: string } & Record<string, OrchardRow | string>)[] };
}

/** Compte d'un bien vivant (24x, ou 234x en cours) d'après le libellé « code — libellé » des options. */
export const isLivingAccount = (label: string | undefined) => !!label && /^(24|234)/.test(label);

export const STATUS_TONES: Record<string, "ok" | "todo" | "gap" | "info" | "neutral"> = {
  waiting: "todo", in_use: "ok", depreciated: "info", sold: "neutral", scrapped: "neutral",
};
