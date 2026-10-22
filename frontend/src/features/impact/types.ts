// Visibilité & Impact : tableau de bord par période (API /api/v1/impact).
import type { IntegrationState } from "../../components/IntegrationNotice";
import type { MonthOption } from "../../components/MonthSelect";

export const IMPACT_KEY = ["impact"];

export const PERIOD_DEFAULTS = { gran: "", month: "", quarter: "", year: "", start: "", end: "" };
export type PeriodParams = typeof PERIOD_DEFAULTS;

export interface Kpi {
  key: string; label: string; unit: string; value: number | null; formatted: string; delta_pct: number | null;
  trend: (number | null)[]; source: string; source_label: string; origin: string; higher_is_better: boolean; available: boolean;
}

export interface ImpactView {
  period: { label: string; start: string; end: string; gran: string };
  current: PeriodParams;
  highlights: { key: string; label: string; formatted: string; available: boolean; icon: string }[];
  sections: { key: string; label: string; kpis: Kpi[] }[];
  sources: { source: string; label: string; status: string; fresh_at: string | null }[];
  meta: { months: MonthOption[]; years: string[]; ga4: IntegrationState; facebook: IntegrationState; export_url: string };
}

export function periodQuery(params: Partial<PeriodParams>): string {
  const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
  return query ? `?${query}` : "";
}

/** « ▲ 12,5 % » ; bon sens selon l'indicateur (une baisse peut être une bonne nouvelle). */
export function delta(kpi: Pick<Kpi, "delta_pct" | "higher_is_better">): { text: string; good: boolean } | null {
  if (kpi.delta_pct === null) return null;
  const up = kpi.delta_pct >= 0;
  const text = `${up ? "▲" : "▼"} ${Math.abs(kpi.delta_pct).toFixed(1).replace(".", ",")} %`;
  return { text, good: up === kpi.higher_is_better };
}
