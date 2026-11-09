// Lot AG6.e : régime BA, simulation, revenus accessoires (Structure › Fiscalité).
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { BaRegimePanel, type BaRegimeView } from "./BaRegimePanel";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const VIEW: BaRegimeView = {
  fiscal_year: { id: 7, label: "2026", end_date: "2026-12-31" },
  regime: { years: [{ year: 2024, threshold_cents: 12000000, agricultural_ttc_cents: null, accessory_ttc_cents: null, source: "lyvre" }],
    average_cents: 13000000, thresholds: { micro_cents: 12920000, normal_cents: 42100000, detail: null }, current: "micro", current_label: "Micro-BA",
    expected: "simplified", expected_label: "Réel simplifié", next_start: "2027-01-01", micro_allowed: true, micro_reason: null,
    change: { direction: "up", label: "Réel simplifié de plein droit à compter du 01/01/2027 (moyenne au-dessus du seuil)." }, warnings: [] },
  simulation: { micro_allowed: true, micro_reason: null, average_cents: 13000000, micro_profit_cents: 1690000, real_result_cents: 3000000,
    real_basis: "résultat fiscal", best: "micro", deadline: "Option pour le réel…", notes: [] },
  accessory: { applicable: true, span: [2023, 2024, 2025], young: false, agricultural_avg_cents: 10000000, accessory_avg_cents: 6000000,
    limit_ratio_cents: 5000000, limit_cap_cents: 10000000, multiplier: 1, exceeded: true, consequence: "is", current_share_bp: 0,
    accounts: [{ id: 3, code: "7083", label: "Locations diverses", class: "accessory", used: false },
      { id: 4, code: "7011", label: "Ventes de produits végétaux", class: null, used: true },
      { id: 5, code: "7012", label: "Ventes de produits animaux", class: null, used: false }] },
  history: [], classes: [{ value: "accessory", label: "Recette accessoire BIC / BNC (art. 75)" }],
};

afterEach(() => vi.restoreAllMocks());

describe("Régime BA", () => {
  it("moyenne, changement de régime et revenus accessoires", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("ba-regime") ? { item: VIEW }
      : { items: [{ id: 7, label: "2026", status: "open" }] })) as typeof globalThis.fetch);
    renderWithProviders(<BaRegimePanel editable />, { route: "/configuration/organization/?tab=tax",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText(/Réel simplifié de plein droit/)).toBeInTheDocument();
    expect(screen.getByText(/IS de plein droit/)).toBeInTheDocument();
    expect(screen.getAllByLabelText("Repérage 7083").length).toBeGreaterThan(0);
    expect(screen.getAllByLabelText("Repérage 7011").length).toBeGreaterThan(0);
    expect(screen.queryByLabelText("Repérage 7012")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
  });

  it("limite de 50 % inconnue sans recettes agricoles", async () => {
    const view = { ...VIEW, accessory: { ...VIEW.accessory, agricultural_avg_cents: null, limit_ratio_cents: null, exceeded: false } };
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("ba-regime") ? { item: view }
      : { items: [{ id: 7, label: "2026", status: "open" }] })) as typeof globalThis.fetch);
    renderWithProviders(<BaRegimePanel editable={false} />, { route: "/configuration/organization/?tab=tax", session: TEST_SESSION });
    expect(await screen.findByText(/inconnue \(recettes agricoles 2023–2025 à saisir/)).toBeInTheDocument();
  });
});
