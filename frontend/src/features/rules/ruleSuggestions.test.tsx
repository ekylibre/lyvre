// Règles proposées depuis un mois : seules les propositions à créer ou recréer sont cochées et envoyées.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { RuleSuggestions, type Suggestion } from "./RuleSuggestions";

const base = { reason: "", accounts: ["6061"], count: 1, sources: { "facture d'achat": 1 }, examples: ["PRLV FREE PRO 12"],
  rule: null, shadowed_by: null };
const ITEMS: Suggestion[] = [
  { ...base, pattern: "FREE PRO", status: "new", creatable: true, entity: "Free", account_code: "6061" },
  { ...base, pattern: "TELECOM SERVICES", status: "conflict", creatable: false, entity: "Orange", account_code: null,
    accounts: ["6061", "6262"], reason: "2 comptes pour ce libellé : règle à écrire à la main." },
];

afterEach(() => vi.restoreAllMocks());

describe("RuleSuggestions", () => {
  it("coche les règles à créer et envoie les motifs retenus", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (_url, init) =>
      new Response(JSON.stringify(init?.method === "POST" ? { result: { created: 1, updated: 0 }, notices: [] }
        : { items: ITEMS }), { status: 200 }));
    const onDone = vi.fn();
    renderWithProviders(<RuleSuggestions invalidate={[["rules"]]} onDone={onDone} />);
    expect(await screen.findByText("FREE PRO")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Retenir FREE PRO" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Retenir TELECOM SERVICES" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Créer ou recréer 1 règle" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body)).patterns).toEqual(["FREE PRO"]);
  });
});
