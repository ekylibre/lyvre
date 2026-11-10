// Calculettes (lot AG12) : spécification, préremplissage, résultat (gabarit commun, C1).
export const TOOLS_KEY = ["calculators"] as const;

export interface CalcInput {
  key: string; label: string; kind: "money" | "number" | "integer" | "percent" | "date" | "choice" | "text" | "point";
  unit: string | null; required: boolean; choices: { value: string; label: string }[] | null; help: string | null;
  default: string | null;
}

export interface CalcParam {
  key: string; value: unknown; missing: boolean; valid_from: string | null; valid_to: string | null; source: string | null;
  source_label: string | null; verified_on: string | null; reliability: string | null;
}

export interface CalcSpec {
  code: string; number: string; title: string; category: string; category_label: string; summary: string;
  charts: string[]; prefillable: boolean; inputs: CalcInput[]; example: Record<string, string>; method: string;
  sources: { label: string; url: string }[]; prefill_label: string | null;
  prefill?: Record<string, { value: string; origin: string }>; prefill_options?: { value: string; label: string }[] | null; prefill_empty?: string | null;
  params?: CalcParam[];
}

export interface CalcResult {
  headline: { label: string; value: string }[]; details: { label: string; value: string }[];
  table: { columns: string[]; rows: (string | number)[][] } | null; warnings: string[];
  actions: { label: string; route: string }[]; params: CalcParam[]; on: string; text: string;
  /** Calculettes géographiques (04, 07) : carte du résultat. */
  map?: { center: [number, number]; zoom: number; features: import("geojson").FeatureCollection | null } | null;
}
