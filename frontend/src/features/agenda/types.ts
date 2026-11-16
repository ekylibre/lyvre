// Échéancier de l'exploitation (lots AG9a.b, AG9a.c) : miroir de `GET /api/v1/agenda`.
import type { Tone } from "../../components/StatusBadge";

export const AGENDA_KEY = ["agenda"];

export type AgendaStatus = "done" | "skipped" | "ready" | "late" | "this_week" | "to_prepare" | "upcoming";
type Option = { value: string; label: string };

export interface Occurrence {
  key: string; deadline_id: string; fiche_id: string; label: string; title: string; domain: string; organism: string;
  date: string; period: string; status: AgendaStatus; timing: AgendaStatus; to_confirm: boolean; note: string | null;
  edi_date: string | null; amount_cents: number | null; amount_proposed: boolean; managed: boolean; link: string | null;
  action: { label: string; route?: string; url?: string } | null; quiet: boolean; reminder_only: boolean;
  reliability: string; reminder_from: string; payment: boolean; unlinked: boolean;
  state: {
    id: number; status: "done" | "skipped"; done_on: string | null; origin: "manual" | "bank"; note: string | null;
    transaction: BankDebit | null;
  } | null;
}

/** Débit bancaire rattaché à une échéance ou proposé pour l'être. */
export interface BankDebit {
  id: number; bank_account_id: number; date: string; label: string; amount_cents: number; amount_matches?: boolean;
}

/** Point à vérifier (lot AG9a.c, design § 6.2). */
export interface Detection {
  id: string; level: "warning" | "info"; title: string; detail: string; link: string | null; link_label: string | null;
}

export interface Fiche {
  id: string; title: string; domain: string; domain_label: string; organism: string; summary: string;
  prepare: string[] | null; lyvre_data: string | null; penalties: string | null; links: string[] | null;
  reliability: string; reminder_only: boolean | null;
}

export interface AgendaResponse {
  items: Occurrence[]; questions: string[]; detections: Detection[]; today: string; start: string; end: string;
  fiches: Record<string, Fiche>; statuses: Option[]; domains: Option[];
}

export const STATUS_TONES: Record<AgendaStatus, Tone> = {
  done: "ok", skipped: "neutral", ready: "info", late: "gap", this_week: "todo", to_prepare: "neutral", upcoming: "neutral",
};

/** Blocs de la vue liste, dans l'ordre. */
export const BLOCKS: { status: AgendaStatus[]; title: string }[] = [
  { status: ["late"], title: "En retard" },
  { status: ["this_week"], title: "Cette semaine" },
  { status: ["ready", "to_prepare"], title: "À préparer (d'ici 45 jours)" },
  { status: ["upcoming"], title: "À venir" },
  { status: ["done", "skipped"], title: "Faites ou ignorées" },
];

export const DOMAIN_COLORS: Record<string, string> = {
  tva: "lichen", fiscal: "ardoise", social: "paille", pac: "lime", filieres: "teal", divers: "gray",
};

/** Ligne du résumé du lundi (lot AG9a.d), miroir de `GET /api/v1/agenda/summary`. */
export interface SummaryLine {
  key: string; label: string; title: string; organism: string; date: string; period: string; status: AgendaStatus;
  amount_cents: number | null; amount_proposed: boolean; link: string; action_label: string | null;
  penalties: string | null; missing: string[];
}

export interface WeeklySummary {
  day: string; week: string; monday: string; late: SummaryLine[]; this_week: SummaryLine[]; to_prepare: SummaryLine[];
  to_check: Detection[]; counts: { late: number; this_week: number; to_prepare: number; to_check: number }; empty: boolean;
}

export interface AgendaSubscription { subscribed: boolean; email: string; available: boolean; last_sent_week: string | null }
