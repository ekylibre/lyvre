import { describe, expect, it } from "vitest";
import { deleteMessage } from "./types";

describe("message de suppression d'une facture d'achat", () => {
  it("saisie non envoyée : rien sur Qonto", () => {
    expect(deleteMessage({ source: "manual", in_qonto: false, journal_entry_id: null })).toBeUndefined();
    expect(deleteMessage({ source: "manual", in_qonto: false, journal_entry_id: 3 })).toBe("Son écriture d'achat sera supprimée aussi.");
  });

  it("présente dans Qonto : à supprimer aussi là-bas pour ne pas revenir", () => {
    expect(deleteMessage({ source: "manual", in_qonto: true, journal_entry_id: null })).toBe(
      "Elle a été déposée dans Qonto et y reste : supprimez-la aussi dans Qonto si vous ne voulez pas la voir revenir : la synchronisation la réimporte dès qu'elle y est modifiée.");
    expect(deleteMessage({ source: "qonto", in_qonto: true, journal_entry_id: 3 })).toBe(
      "Son écriture d'achat sera supprimée aussi. Elle reste dans Qonto : supprimez-la aussi dans Qonto si vous ne voulez pas la voir revenir : la synchronisation la réimporte dès qu'elle y est modifiée.");
  });
});
