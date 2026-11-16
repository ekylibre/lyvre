// Lot NV3 : page d'accueil des éditions comptables, exercice transmis à l'édition ouverte.
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import ReportsHubPage from "./ReportsHubPage";

const META = { fiscal_years: [{ value: "7", label: "2026" }], fiscal_year: { id: 7, label: "2026", start_date: "2026-01-01",
  end_date: "2026-12-31" }, previous: null };

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation((() => Promise.resolve(new Response(JSON.stringify({ items: [
    { key: "balance", title: "Balance", icon: "scale", summary: "Mouvements et soldes.", url: "/reports/balance", exports: [] },
    { key: "compte_resultat", title: "Compte de résultat", icon: "chart-line", summary: "Produits et charges.",
      url: "/reports/compte-de-resultat", exports: [{ label: "CSV", url: "/reports/compte-de-resultat.csv?fy_id=7" }] },
  ], meta: META }), { status: 200 }))) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

it("une carte par édition, avec l'exercice et les exports", async () => {
  renderWithProviders(<ReportsHubPage />);
  expect(await screen.findByRole("link", { name: "Balance" })).toHaveAttribute("href", "/reports/balance?fy_id=7");
  expect(screen.getByRole("link", { name: "Compte de résultat" })).toHaveAttribute("href", "/reports/compte-de-resultat?fy_id=7");
  expect(screen.getByRole("link", { name: "CSV" })).toHaveAttribute("href", "/reports/compte-de-resultat.csv?fy_id=7");
});
