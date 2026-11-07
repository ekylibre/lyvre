// Lot AG4.a : inventaire de clôture.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import InventoryPage, { type StockView } from "./InventoryPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const LINE = {
  id: 1, category: "supplies", account: { id: 3, code: "31111", label: "Engrais et amendements" }, variation_account: { id: 4, code: "6031" },
  label: "Ammonitrate", production: null, quantity: "10.500", unit: "t", method: "actual", standard_id: null, standard: null,
  market_price_cents: null, price_source: null, price_reference: null, flat_rate: null, unit_value_cents: 25000, value_cents: 262500,
  depreciation_cents: null, depreciation_reason: null, notes: null, warnings: [], purchase_account: "60111", lot_id: null, heads: null, gap_reason: null, crop_advance_id: null,
  fiscal: { fiscal_method: "none", fiscal_value_cents: 262500, gap_cents: 0, warnings: [], allowed: ["none", "manual"], fiscal_reason: null, manual_cents: null },
};
const VIEW: StockView = {
  item: { fiscal_year: { id: 7, label: "2026", end_date: "2026-12-31", status: "open" }, editable: true, items: [LINE],
    totals: { supplies: { value_cents: 262500, depreciation_cents: 0, lines: 1 } }, total_cents: 262500, discounts: {},
    counted_on: null, flat_allowed: false, has_previous: true, purchases: { "60111": 1200000 },
    opening: [{ code: "31111", label: "Engrais", balance_cents: 669266, counted: true },
      { code: "3113", label: "Animaux (cycle court)", balance_cents: 150000, counted: false }], lots: [], crop_advances: [],
    fiscal: { accounting_cents: 262500, fiscal_cents: 262500, gap_cents: 0, missing: 0, flat: false, frozen: false, frozen_since: null } },
  meta: {
    categories: [{ key: "supplies", label: "Approvisionnements", group: "supplies", methods: ["actual", "standard"], retail: false, accounts: [{ prefix: "3111", variation: "6031" }] },
      { key: "finished", label: "Produits finis", group: "products", methods: ["actual", "standard", "retail", "flat"], retail: true, accounts: [{ prefix: "355", variation: "71355" }] }],
    groups: [{ value: "supplies", label: "Approvisionnements" }, { value: "products", label: "En-cours et produits" }],
    methods: [{ value: "actual", label: "Coût réel" }, { value: "standard", label: "Coût standard (barème)" }, { value: "retail", label: "Prix de détail moins décote" }, { value: "flat", label: "Méthode forfaitaire (réel simplifié)" }],
    units: [{ value: "t", label: "tonne" }, { value: "head", label: "tête" }], flat_rates: [], standards: [],
    price_references: { source: "Cotations", week: "2026-W44", items: [] },
  },
  files: [],
  entry: { entry: null, stale: false, problems: [], opening_cents: 819266, final_cents: 262500, variation_cents: -556766, depreciation_cents: 0, lines: 1 },
};

afterEach(() => vi.restoreAllMocks());

describe("Inventaire de clôture", () => {
  it("lignes du groupe, repère des achats, stocks initiaux à recompter", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("/stock")
      ? VIEW : { items: [{ id: 7, label: "2026", status: "open", start_date: "2026-01-01", end_date: "2026-12-31" }] })) as typeof globalThis.fetch);
    renderWithProviders(<InventoryPage />, { route: "/inventory/",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("Ammonitrate")).toBeInTheDocument();
    expect(screen.getByText("31111 / 6031")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Passer l'écriture" })).toBeEnabled();
    expect(screen.getByText("non passée")).toBeInTheDocument();
    expect(screen.getByText(/achats 60111 de l'exercice/)).toBeInTheDocument();
    expect(screen.getByText(/3113 Animaux \(cycle court\)/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reprendre l'exercice précédent" })).not.toBeInTheDocument();   // inventaire non vide
    expect(screen.getByLabelText("Produits finis")).toBeInTheDocument();            // décote : catégories au prix de détail seulement
    await userEvent.click(screen.getByRole("button", { name: "Ajouter une ligne" }));
    expect(await screen.findByRole("button", { name: "Ajouter la ligne" })).toBeInTheDocument();
  });

  it("valeur fiscale et écart quand une option est en vigueur", async () => {
    const view = { ...VIEW, item: { ...VIEW.item, fiscal: { ...VIEW.item.fiscal, flat: true, fiscal_cents: 300000, gap_cents: 37500 },
      items: [{ ...LINE, fiscal: { ...LINE.fiscal, fiscal_method: "flat", fiscal_value_cents: 300000, gap_cents: 37500, allowed: ["none", "manual", "flat"] } }] } };
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("/stock")
      ? view : { items: [{ id: 7, label: "2026", status: "open", start_date: "2026-01-01", end_date: "2026-12-31" }] })) as typeof globalThis.fetch);
    renderWithProviders(<InventoryPage />, { route: "/inventory/",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByRole("columnheader", { name: "Valeur fiscale" })).toBeInTheDocument();
    expect(screen.getByText("Méthode forfaitaire (art. 74 b)", { exact: false })).toBeInTheDocument();
  });

  it("blocage 72 B bis : case de rotation lente sur la ligne (lot CG3.d)", async () => {
    const view = { ...VIEW, item: { ...VIEW.item, fiscal: { ...VIEW.item.fiscal, frozen: true, frozen_since: "2025-01-01" },
      items: [{ ...LINE, label: "Cognac", fiscal: { ...LINE.fiscal, fiscal_method: "frozen", allowed: ["frozen", "manual"],
        freezable: true, slow: true, slow_rotation: true } }] } };
    vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => json(String(url).includes("/stock")
      ? view : { items: [{ id: 7, label: "2026", status: "open", start_date: "2026-01-01", end_date: "2026-12-31" }] })) as typeof globalThis.fetch);
    renderWithProviders(<InventoryPage />, { route: "/inventory/",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    await userEvent.click(await screen.findByText("Cognac"));
    expect(await screen.findByRole("checkbox", { name: /Rotation de plus d'un an/ })).toBeChecked();
  });
});
