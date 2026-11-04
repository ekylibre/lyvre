// Lot AG2.d : livres de TVA (ventes, achats) et contrôle avec la CA12A.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import VatBooksPage from "./VatBooksPage";
import type { PurchasesBook, SalesBook } from "./types";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const SALES: SalesBook = {
  start: "2026-01-01", end: "2026-12-31",
  items: [{ date: "2026-03-02", entry_id: 3, reference: "OD-3", label: "Vente de porcs", entity: "Abattoir", code: "V20",
    code_label: "", line: "04", category: "Taxables à 20 %", base_cents: 100000, tax_cents: 20000 }],
  totals: [{ line: "04", category: "Taxables à 20 %", base_cents: 100000, tax_cents: 20000 }],
  total: { base_cents: 100000, tax_cents: 20000 },
  control: { form: "CA12A", validated: false, ok: false, lines: [{ line: "04", label: "Taux normal 20 %", book_base: 1000,
    book_tax: 200, return_base: 1200, return_tax: 240, ok: false }] },
};
const PURCHASES: PurchasesBook = {
  start: "2026-01-01", end: "2026-12-31",
  items: [{ date: "2026-08-03", entry_id: 9, reference: "OD-9", label: "Assurance", entity: "", group: "other",
    group_label: "Autres biens et services", codes: [], ht_cents: 50000, deductible_cents: 0, reverse_charge_cents: 0,
    non_deductible: true }],
  totals: [{ group: "other", label: "Autres biens et services", ht_cents: 50000, deductible_cents: 0,
    reverse_charge_cents: 0, non_deductible_ht_cents: 50000 }],
  control: null,
};

afterEach(() => vi.restoreAllMocks());

describe("Livres de TVA", () => {
  it("livre des ventes : écart signalé ligne par ligne", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json(SALES)) as typeof fetch);
    renderWithProviders(<VatBooksPage />, { route: "/vat-returns/books?period=2026-A" });
    expect(await screen.findByText("Écart avec la CA12A")).toBeInTheDocument();
    expect(screen.getByText(/Lignes 04/)).toBeInTheDocument();
    expect(screen.getByText("1200 € / 240 €")).toBeInTheDocument();
  });

  it("livre des achats : achat non déductible", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json(PURCHASES)) as typeof fetch);
    renderWithProviders(<VatBooksPage />, { route: "/vat-returns/books?book=purchases" });
    expect(await screen.findByText("non déductible")).toBeInTheDocument();
    expect(screen.getByText("Assurance")).toBeInTheDocument();
  });
});
