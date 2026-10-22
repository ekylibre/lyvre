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

/** « 2026-10-02 » → « 02/10/2026 » ; vide → « — ». */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
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
