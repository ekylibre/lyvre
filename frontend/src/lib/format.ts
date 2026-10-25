// Formats français partagés par les écrans (montants en centimes, dates ISO).
import { formatEuros as formatEurosRaw } from "./money";

/**
 * Centimes → « 1 248,00 € » selon la charte : espace fine insécable pour les milliers,
 * signe moins typographique « − » (U+2212), `+` sur demande (crédits d'un relevé).
 */
export function formatEuros(cents: number, options: { plus?: boolean } = {}): string {
  const text = formatEurosRaw(Math.abs(cents));
  if (cents < 0) return `\u2212${text}`;
  return options.plus && cents > 0 ? `+${text}` : text;
}

const COMPACT = new Intl.NumberFormat("fr-FR", { notation: "compact", maximumFractionDigits: 1 });

/** Euros (pas centimes) → « 12,3 k€ », « 1,5 M€ », « 950 € » : graduations des axes de graphique, où le
 * montant complet ne tient pas (l'infobulle le donne). */
export function formatEurosShort(euros: number): string {
  const number = COMPACT.format(Math.abs(euros));
  const text = /[kM]$/.test(number) ? `${number}€` : `${number}\u202f€`;
  return euros < 0 ? `\u2212${text}` : text;
}

/** Graduations en euros de l'axe Y (Mantine Charts) : format court, largeur suffisante. */
export const EUROS_Y_AXIS = { tickFormatter: formatEurosShort, width: 64 };

/** « 2026-10-02 » → « 02/10/2026 » ; vide → « — ». */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
}

/** « 2026-10-02T14:30:00 » → « 02/10/2026 14:30 » (heure telle qu'enregistrée) ; vide → « — ». */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const time = iso.slice(11, 16);
  return time ? `${formatDate(iso)} ${time}` : formatDate(iso);
}

const COLLATOR = new Intl.Collator("fr", { numeric: true, sensitivity: "base" });

/** Comparaison pour les tris (textes à la française, nombres, vides en dernier). */
export function compareValues(a: unknown, b: unknown): number {
  if (a === b) return 0;
  if (a === null || a === undefined || a === "") return 1;
  if (b === null || b === undefined || b === "") return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  if (typeof a === "boolean" && typeof b === "boolean") return Number(a) - Number(b);
  return COLLATOR.compare(String(a), String(b));
}

/** Code NAF tel que Sirene le renvoie (« 6820B ») → affichage officiel (« 68.20B »). */
export function formatNaf(code: string | null | undefined): string {
  return code && code.length === 5 ? `${code.slice(0, 2)}.${code.slice(2)}` : code ?? "";
}
