// Intégrations : état des services externes de l'instance (API /api/v1/integrations).
import type { Tone } from "../../components/StatusBadge";

export const INTEGRATIONS_KEY = ["integrations"];

export interface CheckResult { ok: boolean; message: string; checked_at: string | null; duration_ms: number }

export interface Integration {
  slug: string; label: string; description: string; status: "ok" | "error" | "untested" | "unconfigured" | "disabled";
  status_label: string; enabled: boolean; configured: boolean; check_outdated: boolean; last_check: CheckResult | null;
  /** Recommandée pour la structure de l'instance (Qonto pour une SCI, HelloAsso pour une association). */
  recommended?: boolean;
}

/** Ordre d'affichage : activées, puis recommandées, puis les autres (ordre du serveur sinon). */
export function sortIntegrations(items: Integration[]): Integration[] {
  const rank = (v: Integration) => (v.enabled ? 0 : v.recommended ? 1 : 2);
  return items.map((v, i) => [v, i] as const).sort(([a, i], [b, j]) => rank(a) - rank(b) || i - j).map(([v]) => v);
}

export interface Field {
  key: string; label: string; input: "text" | "password" | "textarea" | "brevo_list"; help: string; required: boolean; secret: boolean;
  source: "db" | "env" | "none"; value: string; env_value: string | null;
}

export interface IntegrationDetail {
  item: Integration & {
    sync_tracked: boolean;
    /** Périmètre (Qonto : relevés de compte, achats, ventes) ; vide si l'intégration n'en a pas. */
    scopes?: { value: string; label: string; checked: boolean }[];
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
