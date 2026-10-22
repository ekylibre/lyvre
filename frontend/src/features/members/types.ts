import type { IntegrationState } from "../../components/IntegrationNotice";
import type { Tone } from "../../components/StatusBadge";

export interface Member {
  id: number; name: string; email: string | null; is_member: boolean; is_benevole: boolean;
  notes: string | null; last_helloasso_membership: string | null; last_pos_membership: string | null;
  birthday: string; status: string; status_label: string; color: "red" | "orange" | "green";
}

export const MEMBERS_KEY = ["members"];

/** Échéance de l'adhésion : dépassée, dans moins de 30 jours, à jour. */
export const EXPIRY: Record<Member["color"], { tone: Tone; label: string }> = {
  red: { tone: "gap", label: "Échue" },
  orange: { tone: "todo", label: "Bientôt échue" },
  green: { tone: "ok", label: "À jour" },
};

export interface Integrations { integrations: Record<"helloasso" | "odoo" | "smtp", IntegrationState> }

export const MEMBER_FILTERS = { q: "", date_from: "", date_to: "", sort_by: "name", sort: "asc" };

export function filterQuery(params: Record<string, string>): string {
  const search = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
  const text = search.toString();
  return text ? `?${text}` : "";
}
