// Lot AG1.d : onglets « Livre des recettes » et « Micro-BA » des états simplifiés d'une exploitation agricole.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Session } from "../../api/session";
import SimpleReportsPage from "./SimpleReportsPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const session = (chart: "agri" | "asso"): Session => ({ ...TEST_SESSION, role: "admin",
  permissions: { write: true, instance_admin: true }, instance: { ...TEST_SESSION.instance!, chart, bookkeeping: "simple" } });
const zero = { amount_cents: 0, previous_cents: 0 };

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.startsWith("/api/v1/simple/reports/income-statement")) return json({ fiscal_year_id: 1, fiscal_years: [],
      fiscal_year: "2026", previous_year: null, rows: [], totals: { income: zero, expense: zero }, result: zero });
    if (url.startsWith("/api/v1/simple/reports/treasury")) return json({ fiscal_year_id: 1, fiscal_years: [], fiscal_year: "2026",
      start_date: "2026-01-01", end_date: "2026-12-31", rows: [], total: { start_cents: 0, end_cents: 0, change_cents: 0 }, result_cents: 0 });
    if (url.startsWith("/api/v1/simple/reports/receipts-book")) return json({ year: 2026, grouping_cents: 7600,
      export_url: "/simple/reports/receipts-book.xlsx?year=2026&group_small=1",
      items: [{ date: "2026-03-01", label: "Ventes au détail du jour (2)", entity: null, category: "Ventes de produits végétaux",
        excluded: false, amount_cents: 10000, grouped: 2 },
      { date: "2026-05-02", label: "Vente du broyeur", entity: null, category: "Cessions de matériel", excluded: true, amount_cents: 120000 }],
      quarters: [1, 2, 3, 4].map((quarter) => ({ quarter, retained_cents: quarter === 1 ? 10000 : 0, excluded_cents: 0 })),
      total: { retained_cents: 10000, excluded_cents: 120000, receipts_cents: 130000 } });
    if (url.startsWith("/api/v1/simple/reports/micro-ba")) return json({ year: 2026, average_cents: 3600000, allowance_bp: 8700,
      minimum_cents: 30500, profit_cents: 468000, threshold_cents: 12920000, warnings: [],
      reliability: { allowance: "R", minimum: "R", threshold: "I" },
      years: [{ year: 2026, receipts_cents: 3600000, source: "lyvre", note: null },
        { year: 2025, receipts_cents: 3500000, source: "entered", note: null },
        { year: 2024, receipts_cents: 3700000, source: "entered", note: null }] });
    return json({ items: [] });
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("micro-BA", () => {
  it("livre des recettes : regroupement et recette exclue", async () => {
    renderWithProviders(<SimpleReportsPage />, { session: session("agri"), route: "/simple/reports?tab=book" });
    expect(await screen.findByText("Ventes au détail du jour (2)")).toBeInTheDocument();
    expect(screen.getByText("exclue du micro-BA")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Exporter en XLSX" })).toBeInTheDocument();
  });

  it("récapitulatif : années, origine, bénéfice forfaitaire", async () => {
    renderWithProviders(<SimpleReportsPage />, { session: session("agri"), route: "/simple/reports?tab=micro" });
    expect(await screen.findByText("Bénéfice forfaitaire")).toBeInTheDocument();
    expect(screen.getAllByText("saisie")).toHaveLength(2);
    expect(screen.getByText("87 %")).toBeInTheDocument();
  });

  it("pas d'onglets micro-BA pour une association", async () => {
    renderWithProviders(<SimpleReportsPage />, { session: session("asso") });
    expect(await screen.findByRole("tab", { name: "Compte de résultat" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Livre des recettes" })).not.toBeInTheDocument();
  });
});
