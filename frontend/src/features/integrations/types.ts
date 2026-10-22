// Intégrations : état des services externes de l'instance (API /api/v1/integrations).
import type { Tone } from "../../components/StatusBadge";

export const INTEGRATIONS_KEY = ["integrations"];

export interface CheckResult { ok: boolean; message: string; checked_at: string | null; duration_ms: number }

export interface Integration {
  slug: string; label: string; description: string; status: "ok" | "error" | "untested" | "unconfigured" | "disabled";
  status_label: string; enabled: boolean; configured: boolean; check_outdated: boolean; last_check: CheckResult | null;
}

export interface Field {
  key: string; label: string; input: "text" | "password" | "textarea"; help: string; required: boolean; secret: boolean;
  source: "db" | "env" | "none"; value: string; env_value: string | null;
}

export interface IntegrationDetail {
  item: Integration & {
    sync_tracked: boolean;
    last_sync: { status: string; started_at: string | null; finished_at: string | null; message: string | null;
      imported: number | null; errors: string[]; url: string; link_label: string } | null;
  };
  fields: Field[];
}

export const STATUS_TONES: Record<Integration["status"], Tone> = {
  ok: "ok", error: "gap", untested: "info", unconfigured: "todo", disabled: "neutral",
};

/** Horodatage du serveur (UTC sans fuseau) → « 20/10/2026 21:52 » à l'heure locale. */
export function localDateTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(`${iso}Z`).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }).replace(",", "");
}

/** « 20/10/2026 21:52 · 1,2 s ». */
export function checkSummary(check: CheckResult): string {
  return `${localDateTime(check.checked_at)} · ${(check.duration_ms / 1000).toFixed(1).replace(".", ",")} s`;
}
