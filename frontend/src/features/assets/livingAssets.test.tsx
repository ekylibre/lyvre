// Lot AG5.a : bien vivant immobilisé (lot de truies), sortie partielle au coût moyen.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import AssetDetailPage from "./AssetDetailPage";
import type { AssetItem } from "./types";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const LOT: AssetItem = {
  id: 5, parent_id: null, label: "Truies", account: { id: 2, code: "241", label: "Animaux reproducteurs" }, depreciation_account_code: "284",
  acquired_on: "2026-01-01", in_service_date: "2026-01-01", acquisition_cents: 1500000, residual_cents: 0, method: "linear",
  method_label: "Linéaire", duration_months: 60, fiscal_coefficient: null, prior_depreciation_cents: 0, prior_as_of: null,
  project_id: null, project: null, status: "in_use", status_label: "En service", accumulated_cents: 0, net_cents: 1500000,
  disposal_date: null, disposal_price_cents: null, purchase_line_id: null, notes: "", components: [], deletable: false, schedule: [],
  living: { kind: "breeding", species: "Porc", age_class: "Truies", units: 40, origin: null },
};

afterEach(() => vi.restoreAllMocks());

describe("Biens vivants immobilisés", () => {
  it("effectif, valeur par tête et sortie partielle", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ item: LOT, meta: { accounts: [], methods: [], statuses: [], enabled: true } })) as typeof globalThis.fetch);
    renderWithProviders(<Routes><Route path="/assets/:asset_id" element={<AssetDetailPage />} /></Routes>, { route: "/assets/5",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText(/40 Porc/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Sortir de l'actif…" }));
    expect(await screen.findByLabelText("Effectif sorti (sur 40)")).toHaveValue("40");
    expect(screen.getByText(/valeur nette en 6571/)).toBeInTheDocument();
    expect(screen.getByLabelText("Prix de cession")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Abattage sanitaire"));
    expect(screen.getByLabelText("Indemnité (assurance, État)")).toBeInTheDocument();
    expect(screen.getByText(/registre de reconstitution du cheptel/)).toBeInTheDocument();
  });
});
