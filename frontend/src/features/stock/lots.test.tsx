// Lot AG4.b : lots d'animaux.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { LotsPanel, type StockLotItem } from "./LotsPanel";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const LOT: StockLotItem = {
  id: 2, label: "Porc — Porcelets", species: "Porc", age_class: "Porcelets", destination: "sale", destination_label: "Vente",
  account: { id: 9, code: "3113", label: "Animaux (cycle court)" }, average_weight_kg: "25", active: true,
  summary: { opening: 120, opening_source: "previous", movements: {}, entries: 300, exits: 284, theoretical: 136, counted: 135, gap: -1, line_id: 4 },
  movements: [{ id: 5, on: "2026-06-01", kind: "birth", kind_label: "Naissance", heads: 300, sign: 1, note: null, counterpart: null, paired: false }],
};

afterEach(() => vi.restoreAllMocks());

describe("Lots d'animaux", () => {
  it("effectif théorique, écart et mouvements du lot", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ item: LOT })) as typeof globalThis.fetch);
    renderWithProviders(<LotsPanel fyId={7} lots={[LOT]} editable invalidate={[]} />,
      { session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(screen.getByText("136")).toBeInTheDocument();
    expect(screen.getByText("(-1)")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Porc — Porcelets"));
    expect(await screen.findByRole("cell", { name: "Naissance" })).toBeInTheDocument();
    expect(screen.getByText(/théorique 136/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ajouter" })).toBeInTheDocument();
  });
});
