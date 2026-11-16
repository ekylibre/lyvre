// Lot AG10.a : activités proposées après la reprise d'un dossier agricole.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { ActivityProposals } from "./ImportHistoryPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const ITEMS = [
  { account_id: 7, code: "70117111", label: "MAIS GRAINS", name: "Maïs grain", lexicon_reference: "corn", lexicon_name: "Maïs grain",
    family: "plant_farming", activity_id: null },
  { account_id: 8, code: "7011001", label: "TOURNESOL", name: "Tournesol", lexicon_reference: null, lexicon_name: null,
    family: "plant_farming", activity_id: 3 },
];

afterEach(() => vi.restoreAllMocks());

describe("Activités proposées", () => {
  it("liste et crée les activités cochées", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation(((_url: string, init?: RequestInit) =>
      json(init?.method === "POST" ? { activities: 1, rules: 1, items: [], notices: [] } : { items: ITEMS })) as typeof fetch);
    renderWithProviders(<ActivityProposals />);
    expect(await screen.findByText("Activités proposées (2)")).toBeInTheDocument();
    expect(screen.getByText("production Lexicon : Maïs grain")).toBeInTheDocument();
    expect(screen.getByText("activité existante")).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Créer 0 activité(s)" });
    expect(button).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: "Retenir 70117111" }));
    await userEvent.click(screen.getByRole("button", { name: "Créer 1 activité(s)" }));
    await waitFor(() => expect(spy.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === "POST")).toBe(true));
    const post = spy.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST")!;
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ items: [{ account_id: 7 }] });
  });

  it("rien à proposer : rien d'affiché", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ items: [] })) as typeof fetch);
    renderWithProviders(<ActivityProposals />);
    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(screen.queryByText(/Activités proposées/)).toBeNull();
  });
});

describe("Sections Isacompta", () => {
  it("coche et décoche les sections", async () => {
    const { IsaSections } = await import("./ImportHistoryPage");
    const setChosen = vi.fn();
    const info = {
      sections: [{ code: "11111", label: "BLE TENDRE HIVER", unit: "ha", quantity: 20, workshop: "GRANDES CULTURES",
        lexicon_name: "Blé tendre d’hiver", proposed: true },
      { code: "CS02", label: "BATIMENTS", unit: null, quantity: null, workshop: "CHARGES DE STRUCTURE", lexicon_name: null, proposed: false }],
      line_allocations: 2, account_allocations: 2, due_dates: 1, reconciliations: 1, vat_codes: [],
    };
    renderWithProviders(<IsaSections info={info} chosen={["11111"]} setChosen={setChosen} />);
    expect(screen.getByText("Sections analytiques (2)")).toBeInTheDocument();
    expect(screen.getByText("production Lexicon : Blé tendre d’hiver")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Section 11111" })).toBeChecked();
    await userEvent.click(screen.getByRole("checkbox", { name: "Section CS02" }));
    expect(setChosen).toHaveBeenCalledWith(["11111", "CS02"]);
    await userEvent.click(screen.getByRole("checkbox", { name: "Section 11111" }));
    expect(setChosen).toHaveBeenCalledWith([]);
  });
});
