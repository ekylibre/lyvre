// Clés d'API (lot AK1, claudedocs/design_api_mcp_aiffel.md § 9.1) : types et règles de la grille des domaines.
// Le serveur refait tous les contrôles (app/services/api_keys.py).

export type KeyState = "active" | "expired" | "revoked";

export interface ApiKeyItem {
  id: number;
  name: string;
  prefix: string;
  state: KeyState;
  user: { id: number; email: string; full_name: string | null; is_me: boolean };
  read_domains: string[];
  write_domains: string[];
  rate_per_minute: number;
  creations_per_day: number;
  created_at: string;
  expires_at: string;
  revoked_at: string | null;
  last_used_at: string | null;
}

export interface DomainOption { key: string; label: string; description: string; writable: boolean }
export interface MemberOption { id: number; email: string; full_name: string | null; role: string }

export interface ApiKeysMeta {
  domains: DomainOption[];
  members: MemberOption[];
  mcp_url: string | null;
  defaults: { rate_per_minute: number; creations_per_day: number; days: number; max_days: number };
}

export const STATE_LABELS: Record<KeyState, { label: string; tone: "ok" | "neutral" | "gap" }> = {
  active: { label: "Active", tone: "ok" },
  expired: { label: "Expirée", tone: "neutral" },
  revoked: { label: "Révoquée", tone: "gap" },
};

export interface DomainGrid { read: string[]; write: string[] }

/** Cocher l'écriture coche la lecture ; décocher la lecture décoche l'écriture. */
export function toggleDomain(grid: DomainGrid, key: string, access: "read" | "write", on: boolean): DomainGrid {
  const read = new Set(grid.read);
  const write = new Set(grid.write);
  if (access === "write") {
    if (on) { write.add(key); read.add(key); } else write.delete(key);
  } else if (on) read.add(key);
  else { read.delete(key); write.delete(key); }
  return { read: [...read], write: [...write] };
}

/** Écriture possible : domaine ouvert à l'écriture en v1, et utilisateur qui n'est pas expert-comptable. */
export function canWrite(domain: DomainOption, role: string | undefined): boolean {
  return domain.writable && role !== "accountant";
}

/** Date AAAA-MM-JJ dans `days` jours. */
export function isoInDays(days: number, from: Date = new Date()): string {
  const d = new Date(from.getTime());
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Bloc de configuration d'un client MCP (affiché une fois avec la clé). */
export function mcpConfig(url: string | null, token: string): string {
  return JSON.stringify({ mcpServers: { lyvre: { type: "http", url: url ?? "https://<adresse de Lyvre>/mcp",
    headers: { Authorization: `Bearer ${token}` } } } }, null, 2);
}

export function domainSummary(item: ApiKeyItem, domains: DomainOption[]): { label: string; write: boolean }[] {
  const labels = new Map(domains.map((d) => [d.key, d.label]));
  return item.read_domains.map((key) => ({ label: labels.get(key) ?? key, write: item.write_domains.includes(key) }));
}
