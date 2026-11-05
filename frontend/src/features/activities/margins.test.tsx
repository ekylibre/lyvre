// Lot AG8.d : marges par activité et par atelier.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import MarginsPage, { type MarginsView } from "./MarginsPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const S = { classes: {}, production_cents: 5500000, operational_cents: 450000, gross_margin_cents: 5050000, structure_cents: 0, result_cents: 5050000 };
const VIEW: MarginsView = {
  fiscal_year: { id: 7, label: "2026", status: "open" }, campaign: null, campaigns: [2026], deferred_cents: 0, classes: [],
  warnings: ["Lait : mesure de la campagne 2026 à saisir (marge par unité)."],
  productions: [{ ...S, activity_id: 1, activity: "Blé", nature: "main", workshop_id: 1, workshop: "Grandes cultures", campaign_year: 2026,
    unit_label: "ha", measure: "40", gross_margin_per_unit_cents: 126250 }],
  workshops: [{ workshop_id: 1, workshop: "Grandes cultures", measure: "40", unit_label: "ha", production_cents: 5500000, operational_cents: 450000,
    gross_margin_cents: 5050000, gross_margin_per_unit_cents: 126250, structure_cents: 0, result_cents: 5050000 }],
  reconciliation: { accounting_result_cents: 4850000, activities_cents: 5050000, unallocated_cents: -200000, excluded_cents: 0,
    stock_lines_cents: 0, computed_stock_cents: 0, method_gap_cents: 0, note: "Écart de méthode : …" }, frozen: true, frozen_at: "2027-01-15T10:00:00",
  unallocated: { ...S, production_cents: 0, operational_cents: 0, gross_margin_cents: 0, structure_cents: 200000, result_cents: -200000 },
};

afterEach(() => vi.restoreAllMocks());

describe("Marges par activité", () => {
  it("ateliers, activités, marge par unité et non affecté", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("activity-margins") ? { item: VIEW }
      : { items: [{ id: 7, label: "2026", status: "open" }] })) as typeof globalThis.fetch);
    renderWithProviders(<MarginsPage />, { route: "/activities/margins?fiscal_year=7", session: { ...TEST_SESSION, role: "admin" as const } });
    expect(await screen.findByText("Blé")).toBeInTheDocument();
    expect(screen.getByText("Grandes cultures")).toBeInTheDocument();
    expect(screen.getAllByText("40 ha").length).toBe(2);
    expect(screen.getAllByText("Non affecté").length).toBe(2);
    expect(screen.getByText(/mesure de la campagne 2026/)).toBeInTheDocument();
    expect(screen.getByText("Rapprochement avec le résultat comptable")).toBeInTheDocument();
    expect(screen.getByText(/Figé à la clôture/)).toBeInTheDocument();
  });
});
