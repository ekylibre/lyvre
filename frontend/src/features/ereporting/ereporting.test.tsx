// Lot AG10.e : e-reporting des ventes directes (agrégats, jours à exporter, catégories de vente directe).
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import EreportingPage, { DirectSaleCategories, lastMonth, type EreportingData } from "./EreportingPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
afterEach(() => vi.restoreAllMocks());

const DATA: EreportingData = {
  start: "2026-10-01", end: "2026-10-31", base_cents: 22000, tax_cents: 2660, pending_days: ["2026-10-04"], warnings: [],
  days: [
    { date: "2026-10-03", category: "TLB1", category_label: "Livraisons de biens", base_cents: 12000, tax_cents: 660, exported: true,
      subtotals: [{ rate_bp: 550, base_cents: 12000, tax_cents: 660 }] },
    { date: "2026-10-04", category: "TPS1", category_label: "Prestations de services", base_cents: 10000, tax_cents: 2000, exported: false,
      subtotals: [{ rate_bp: 2000, base_cents: 10000, tax_cents: 2000 }] },
  ],
  categories: [{ id: 3, label: "Accueil à la ferme", account: "706", direct_sale: false }], exports: [],
};

describe("E-reporting B2C", () => {
  it("affiche les agrégats et les jours à exporter", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json(DATA)) as typeof fetch);
    renderWithProviders(<EreportingPage />);
    expect(await screen.findByText("1 jour(s) non exporté(s) sur la période.")).toBeInTheDocument();
    expect(screen.getByText("TPS1")).toBeInTheDocument();
    expect(screen.getByText("à exporter")).toBeInTheDocument();
    expect(screen.getByText("exporté")).toBeInTheDocument();
  });

  it("enregistre les catégories de vente directe", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ notices: [] })) as typeof fetch);
    renderWithProviders(<DirectSaleCategories categories={DATA.categories} />);
    await userEvent.click(screen.getByRole("checkbox", { name: "Accueil à la ferme (706)" }));
    await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/v1/ereporting/categories");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ ids: [3] });
  });

  it("période par défaut : dernier mois terminé ; dernière écriture ; partie double sans catégorie", async () => {
    expect(lastMonth(new Date(2026, 10, 10))).toEqual({ start: "2026-10-01", end: "2026-10-31" });
    expect(lastMonth(new Date(2027, 0, 5))).toEqual({ start: "2026-12-01", end: "2026-12-31" });
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ ...DATA, days: [], pending_days: [], categories: [],
      last_entry_date: "2025-01-31" })) as typeof fetch);
    renderWithProviders(<EreportingPage />);
    expect(await screen.findByText(/la dernière écriture date du 31\/01\/2025/)).toBeInTheDocument();
    expect(screen.getByText(/en partie double,\s+les ventes directes sont celles du journal de caisse/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Enregistrer" })).not.toBeInTheDocument();
  });
});
