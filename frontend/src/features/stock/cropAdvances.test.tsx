// Lot AG4.c : avances aux cultures.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { CropAdvancesPanel, type CropAdvanceItem } from "./CropAdvancesPanel";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const ADV: CropAdvanceItem = {
  id: 3, production: "Blé tendre", surface_ha: "10.0000", planted_on: "2025-10-20", campaign: 2026, cycle: "short", account_code: "31151",
  plots: null, method: "actual", method_label: "Coût réel (art. 72 A)", crop_standard_id: null, notes: null, value_cents: 540000,
  warnings: [], line_id: 8, detail: { components: {}, costs: { seeds: 240000, fertilizers: 180000, machinery: 120000 }, months: 4 },
  costs: [{ id: 1, rubric: "machinery", rubric_label: "Frais de matériel", label: "GNR", journal_line_id: 12, base_cents: 300000, share_bp: 4000, amount_cents: 120000 }],
  proposals: [{ journal_line_id: 12, date: "2025-10-15", account: "60614", label: "GNR", amount_cents: 300000, rubric: "machinery",
    rubric_label: "Frais de matériel", selected: true, cost_id: 1, share_used_bp: 4000, share_free_bp: 6000 },
  { journal_line_id: 13, date: "2025-10-15", account: "60112", label: "Semences blé", amount_cents: 240000, rubric: "seeds",
    rubric_label: "Semences et plants", selected: false, cost_id: null, share_used_bp: 0, share_free_bp: 10000 }],
};
const META = { methods: [{ value: "actual", label: "Coût réel (art. 72 A)" }], rubrics: [], components: [], standards: [] };

afterEach(() => vi.restoreAllMocks());

describe("Avances aux cultures", () => {
  it("fiche, charges 72 A cochées et quote-part", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("crop-standards")
      ? { items: [] } : { item: ADV, meta: META })) as typeof globalThis.fetch);
    renderWithProviders(<CropAdvancesPanel fyId={7} advances={[ADV]} editable invalidate={[]} />,
      { session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(screen.getByText("31151")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Blé tendre"));
    expect(await screen.findByRole("checkbox", { name: "Rattacher GNR" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Rattacher Semences blé" })).not.toBeChecked();
    expect(screen.getByText("40 %")).toBeInTheDocument();
    expect(screen.getByText(/Fermage, assurance et frais généraux en sont exclus/)).toBeInTheDocument();
  });
});
