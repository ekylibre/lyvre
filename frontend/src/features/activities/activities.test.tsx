// Lot AG8.a : ateliers, activités et mesures par campagne.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import ActivitiesPage, { type ActivitiesView } from "./ActivitiesPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const VIEW: ActivitiesView = {
  campaign: 2026, campaigns: [2026], totals: [{ unit: "head", unit_label: "têtes", measure: "80.5" }],
  workshops: [{ id: 1, name: "Vaches laitières", family: "animal_farming", family_label: "Élevage", isacompta_code: null, position: 0, archived: false,
    activities: [{ id: 2, workshop_id: 1, name: "Lait", lexicon_reference: "milk_cow", lexicon_name: "Vaches laitières", nature: "main",
      nature_label: "Principale", cycle: "perennial", unit: "head", unit_label: "têtes", cycle_start: "09-01", cycle_stop: "08-31", year_offset: 1,
      isacompta_code: null, archived: false, campaign: { year: 2026, start: "2025-09-01", stop: "2026-08-31", measure: "62", production_id: 4 } }] }],
};
const META = { families: [{ value: "animal_farming", label: "Élevage" }], natures: [{ value: "main", label: "Principale" }], cycles: [], units: [],
  lexicon: { version: "2026.10.07.1", licence: "CC-BY-SA 4.0", provider: "Ekylibre SAS (Lexicon)", url: "" } };

afterEach(() => vi.restoreAllMocks());

describe("Activités", () => {
  it("ateliers, activités, cycle et mesure de la campagne", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("analytic-keys")
      ? { items: [{ id: 1, name: "Surface cultures", basis: "surface", basis_label: "Surface des activités", warnings: [], members: [{ activity_id: 2, activity: "Lait", workshop: "Vaches laitières", share_bp: null }] }],
          meta: { bases: [{ value: "surface", label: "Surface" }], targets: [] } }
      : String(url).includes("analytic-rules") ? { items: [{ id: 3, account_prefix: "70111", target: { kind: "activity", id: 2, label: "Grandes cultures › Blé" } }] }
      : { item: VIEW, meta: META })) as typeof globalThis.fetch);
    renderWithProviders(<ActivitiesPage />, { route: "/activities/?campaign=2026",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect((await screen.findAllByText("Lait")).length).toBeGreaterThan(0);
    expect(screen.getByText("Lexicon : Vaches laitières")).toBeInTheDocument();
    expect(screen.getByText("01/09/2025 → 31/08/2026")).toBeInTheDocument();
    expect(screen.getByLabelText("Mesure Lait 2026")).toHaveValue("62");
    expect(screen.getByText("80,5 têtes")).toBeInTheDocument();
    expect(await screen.findByText("Surface cultures")).toBeInTheDocument();
    expect(screen.getByText("70111 → Grandes cultures › Blé")).toBeInTheDocument();
  });
});
