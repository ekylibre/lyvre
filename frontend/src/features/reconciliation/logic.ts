import type { AttachmentStatus, Suggestion } from "../../lib/types";

/**
 * Suggestion retenue pour un rapprochement « en un geste » (Entrée, ★ en masse) :
 * la mieux notée, à condition qu'aucune autre n'ait le même score.
 */
export function bestSuggestion(suggestions: Suggestion[] | undefined): Suggestion | null {
  if (!suggestions || suggestions.length === 0) return null;
  const [first, second] = suggestions;
  if (second && second.score === first.score) return null;
  return first;
}

/** Index actif après le retrait des lignes `removed` (reste sur la suivante). */
export function activeAfterRemoval(ids: number[], activeId: number | null, removed: Set<number>): number | null {
  if (activeId === null) return null;
  const start = ids.indexOf(activeId);
  if (start === -1) return null;
  for (let i = start; i < ids.length; i++) if (!removed.has(ids[i])) return ids[i];
  for (let i = start - 1; i >= 0; i--) if (!removed.has(ids[i])) return ids[i];
  return null;
}

/** Identifiants entre deux lignes (incluses), dans l'ordre affiché. */
export function rangeIds(ids: number[], fromId: number, toId: number): number[] {
  const a = ids.indexOf(fromId);
  const b = ids.indexOf(toId);
  if (a === -1 || b === -1) return [];
  const [lo, hi] = a < b ? [a, b] : [b, a];
  return ids.slice(lo, hi + 1);
}

export function plural(n: number, one: string, many: string): string {
  return `${n} ${n > 1 ? many : one}`;
}

export const REVERSED_MESSAGE = "Transaction annulée par la banque : elle ne peut pas être rapprochée.";

/** Pastille de justificatif : libellé et ton du badge, ou null (source sans justificatifs). */
export function attachmentBadge(status: AttachmentStatus): { label: string; tone: "ok" | "todo" | "neutral" } | null {
  switch (status) {
    case "ok":
      return { label: "Justificatif", tone: "ok" };
    case "missing":
      return { label: "Justificatif manquant", tone: "todo" };
    case "lost":
      return { label: "Justificatif perdu", tone: "neutral" };
    default:
      return null;
  }
}
