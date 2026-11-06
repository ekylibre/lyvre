// Lot AG11.d : quantités d'inventaire depuis les matières Ekylibre.
import { describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { EkylibreInventoryView, type EkylibreInventoryData } from "./EkylibreInventory";

const DATA: EkylibreInventoryData = {
  fiscal_year: { id: 1, label: "2026", open: true }, inventory_date: "2026-12-31", synced_at: "2026-12-29T18:00:00",
  gap_days: 2, allowed: true, max_gap_days: 7, lines: [{ value: "4", label: "31111 — Ammonitrate", unit: "t" }],
  items: [
    { variant_id: 9, name: "Ammonitrate", matters: 2, quantity: "1700", unit: "kg", raw_unit: "kg", mixed_units: false,
      line: { id: 4, label: "Ammonitrate", account: "31111", quantity: "0", unit: "t" }, link: null, converted: "1.7" },
    { variant_id: 11, name: "Ficelle", matters: 1, quantity: "3", unit: null, raw_unit: "bobine", mixed_units: false,
      line: null, link: null, converted: null },
  ],
};

describe("Quantités depuis Ekylibre", () => {
  it("reporte la ligne rattachée, signale l'unité inconnue", async () => {
    const onApply = vi.fn();
    renderWithProviders(<EkylibreInventoryView data={DATA} onApply={onApply} />);
    expect(screen.getByText("soit 1,7 t")).toBeInTheDocument();
    expect(screen.getByText("unité non reconnue")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Reporter les quantités (1)" }));
    expect(onApply).toHaveBeenCalledWith([{ variant_id: 9, line_id: 4 }]);
  });

  it("refuse une lecture trop éloignée de la date d'inventaire", () => {
    renderWithProviders(<EkylibreInventoryView data={{ ...DATA, allowed: false, gap_days: 20 }} onApply={vi.fn()} />);
    expect(screen.getByText(/à 20 jours de la date d'inventaire/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reporter les quantités/ })).toBeDisabled();
  });
});
