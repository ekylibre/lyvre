// Données du site, lues à la construction (copies de data/*.yml faites par scripts/prebuild.mjs).
// Seules les versions publiées sont exposées, sans la partie `next` ni les précisions `tech`
// (même règle que la page « Nouveautés » de l'application, app/version.py:published).
import { parse } from "yaml";
import changelogRaw from "../data/changelog.yml?raw";
import featuresRaw from "../data/features.yml?raw";

export type Kind = "action" | "new" | "improved" | "fixed";
export type Structure = "asso" | "sci" | "agri" | "societe";

export interface Entry {
  kind: Kind;
  structure?: Structure;
  text: string;
}
export interface Version {
  version: string;
  date: string;
  title: string;
  entries: Entry[];
}
export interface Feature {
  id: string;
  domain: string;
  title: string;
  text: string;
  structures?: Structure[];
  capture?: string;
  since?: string;
  status?: "available" | "soon";
  /** Sous-partie du module (page Fonctionnalités). */
  group?: string;
}
export interface Shot {
  file: string;
  alt: string;
}
export interface Domain {
  id: string;
  emoji: string;
  title: string;
  /** Ce que le module apporte, en une phrase. */
  intro?: string;
  /** Écrans du module, le premier en grand. */
  captures?: Shot[];
}
export interface Audience {
  id: string;
  emoji: string;
  title: string;
  points: string[];
  capture?: string;
  alt?: string;
}
export interface Overview {
  capture: string;
  alt: string;
  title: string;
  caption: string;
}
export interface Highlight {
  emoji: string;
  title: string;
  text: string;
}
export interface Integration {
  name: string;
  usage: string;
  structures: string;
}

/** Libellés repris de app/version.py (STRUCTURES, KINDS). */
export const STRUCTURES: Record<Structure, string> = {
  asso: "Associations",
  sci: "SCI",
  societe: "Sociétés",
  agri: "Exploitations agricoles",
};
export const KINDS: Record<Kind, string> = {
  action: "Action requise",
  new: "Nouveautés",
  improved: "Améliorations",
  fixed: "Corrections",
};

const VERSION = /^\d{4}\.\d{2}\.\d+$/;

function readVersions(): Version[] {
  const data = parse(changelogRaw, { version: "1.1" }) as { versions?: Record<string, unknown>[] };
  return (data.versions ?? []).map((v) => {
    const version = String(v.version);
    if (!VERSION.test(version)) throw new Error(`changelog.yml : version « ${version} » invalide`);
    const entries = ((v.entries as Record<string, unknown>[] | undefined) ?? []).map((e) => ({
      kind: e.kind as Kind,
      ...(e.structure ? { structure: e.structure as Structure } : {}),
      text: String(e.text ?? "").trim(),
    }));
    return { version, date: isoDate(v.date), title: String(v.title ?? ""), entries };
  });
}

function isoDate(value: unknown): string {
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  return String(value);
}

export const versions: Version[] = readVersions();
export const current = versions[0] ?? { version: "0.0.0", date: "", title: "", entries: [] };

const features = parse(featuresRaw) as {
  highlights: Highlight[];
  audiences: Audience[];
  overview: Overview[];
  domains: Domain[];
  features: Feature[];
  integrations: Integration[];
};
export const highlights = features.highlights;
export const audiences = features.audiences;
export const overview = features.overview;
export const domains = features.domains;
export const featureList = features.features;
export const integrations = features.integrations;

export function featuresOf(domain: string): Feature[] {
  return featureList.filter((f) => f.domain === domain);
}

/** Fonctionnalités d'un module par sous-partie (une seule partie sans titre si aucune n'en a). */
export function groupsOf(domain: string): { title?: string; features: Feature[] }[] {
  const out: { title?: string; features: Feature[] }[] = [];
  for (const f of featuresOf(domain)) {
    const last = out.at(-1);
    if (last && last.title === f.group) last.features.push(f);
    else out.push({ title: f.group, features: [f] });
  }
  return out;
}

export function formatDate(iso: string): string {
  const d = new Date(`${iso}T12:00:00Z`);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" });
}

export function byKind(entries: Entry[]): [Kind, Entry[]][] {
  return (Object.keys(KINDS) as Kind[])
    .map((k) => [k, entries.filter((e) => e.kind === k)] as [Kind, Entry[]])
    .filter(([, list]) => list.length > 0);
}

/** « Écran — ce qui change » : l'écran en tête, mis en valeur par la page. */
export function splitEntry(text: string): { where?: string; what: string } {
  const i = text.indexOf(" — ");
  return i > 0 && i < 120 ? { where: text.slice(0, i), what: text.slice(i + 3) } : { what: text };
}

const escapes: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };

/** Markdown en ligne des textes (gras, code), échappé : à passer à set:html. */
export function inline(text: string): string {
  return text
    .replace(/[&<>"]/g, (c) => escapes[c]!)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.+?)`/g, "<code>$1</code>");
}

export function plain(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, "$1").replace(/`(.+?)`/g, "$1");
}
