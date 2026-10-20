import { describe, expect, it } from "vitest";
import { activeAfterRemoval, attachmentBadge, bestSuggestion, rangeIds } from "./logic";
import type { Suggestion } from "../../lib/types";

const s = (id: number, score: number): Suggestion => ({
  journal_line_id: id, entry_id: id, reference: `R${id}`, entry_date: "2026-03-10",
  label: "", account_code: "512", amount_cents: -100, score,
});

describe("bestSuggestion", () => {
  it("retient la mieux notée si elle est seule à ce score", () => {
    expect(bestSuggestion([s(1, 2), s(2, 1)])?.journal_line_id).toBe(1);
    expect(bestSuggestion([s(1, 1)])?.journal_line_id).toBe(1);
  });
  it("refuse une égalité ou une liste vide", () => {
    expect(bestSuggestion([s(1, 2), s(2, 2)])).toBeNull();
    expect(bestSuggestion([])).toBeNull();
    expect(bestSuggestion(undefined)).toBeNull();
  });
});

describe("activeAfterRemoval", () => {
  const ids = [10, 20, 30, 40];
  it("passe à la suivante restante", () => {
    expect(activeAfterRemoval(ids, 20, new Set([20, 30]))).toBe(40);
  });
  it("revient à la précédente en fin de liste", () => {
    expect(activeAfterRemoval(ids, 40, new Set([40]))).toBe(30);
  });
  it("reste si la ligne active n'est pas retirée", () => {
    expect(activeAfterRemoval(ids, 10, new Set([30]))).toBe(10);
  });
  it("null quand tout est retiré", () => {
    expect(activeAfterRemoval(ids, 10, new Set(ids))).toBeNull();
  });
});

describe("rangeIds", () => {
  it("dans les deux sens", () => {
    expect(rangeIds([1, 2, 3, 4], 2, 4)).toEqual([2, 3, 4]);
    expect(rangeIds([1, 2, 3, 4], 4, 2)).toEqual([2, 3, 4]);
  });
});

describe("attachmentBadge", () => {
  it("donne un libellé par état et rien quand la source ne connaît pas les justificatifs", () => {
    expect(attachmentBadge("ok")?.label).toBe("Justificatif");
    expect(attachmentBadge("missing")?.label).toBe("Justificatif manquant");
    expect(attachmentBadge("lost")?.label).toBe("Justificatif perdu");
    expect(attachmentBadge(null)).toBeNull();
  });
});
