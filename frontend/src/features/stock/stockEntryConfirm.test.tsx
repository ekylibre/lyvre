// Essai de l'interface (09/11/2026) : confirmation avant une écriture de stock en forte baisse.
import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { StockEntryBar, type StockEntryStatus } from "./StockEntryBar";

const base: StockEntryStatus = { entry: null, stale: false, problems: [], opening_cents: 39997077, final_cents: 0,
  variation_cents: -39997077, depreciation_cents: 0, lines: 6 };
const session = { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } };

describe("Écriture de stock", () => {
  it("demande confirmation quand le stock final est nul", async () => {
    renderWithProviders(<StockEntryBar fyId={1} status={base} editable invalidate={[]} />, { session });
    await userEvent.click(screen.getByRole("button", { name: "Passer l'écriture" }));
    expect(await screen.findByText("Stock final nul : passer l'écriture ?")).toBeInTheDocument();
    expect(screen.getByText(/contre 399\s?970,77 € à l'ouverture/)).toBeInTheDocument();
  });

  it("pas de confirmation pour une variation ordinaire", async () => {
    renderWithProviders(<StockEntryBar fyId={1} status={{ ...base, final_cents: 35000000, variation_cents: -4997077 }}
      editable invalidate={[]} />, { session });
    expect(screen.getByRole("button", { name: "Passer l'écriture" })).toBeInTheDocument();
    expect(screen.queryByText(/passer l'écriture \?/)).not.toBeInTheDocument();
  });
});
