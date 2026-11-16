// Lot CG5.c : stock d'entrée au passage au réel.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { OpeningStockPanel } from "./OpeningStockPanel";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const ITEM = { applies: true, total_cents: 160000, frozen: false, entry: { id: 9, validated: false },
  methods: [{ value: "lower", label: "Prix de revient, ou cours du jour s'il est inférieur" }],
  note: "Stock initial au 01/01/2026, passage du micro-BA au régime réel.",
  lines: [{ id: 1, account_code: "35511", label: "Blé", quantity: "10.000", unit: "t", method: "lower",
    method_label: "Prix de revient, ou cours du jour s'il est inférieur", cost_unit_cents: 18000, market_unit_cents: 16000,
    amount_cents: null, value_cents: 160000 }] };

afterEach(() => vi.restoreAllMocks());

describe("Stock d'entrée au passage au réel", () => {
  it("lignes, écriture à valider et note du stock initial", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ item: ITEM })) as typeof globalThis.fetch);
    renderWithProviders(<OpeningStockPanel fyId={7} units={[{ value: "t", label: "tonne" }]} editable />,
      { session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("Stock d'entrée au passage au réel")).toBeInTheDocument();
    expect(screen.getByText(/écriture d'ouverture passée, à valider/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Repasser l'écriture d'ouverture" })).toBeInTheDocument();
    expect(screen.getByLabelText(/Note du stock initial/)).toHaveValue(ITEM.note);
  });
});
