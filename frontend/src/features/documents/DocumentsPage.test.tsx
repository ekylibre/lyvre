// Lot NV5 : navigateur des documents (types, filtre dans l'adresse, aperçu).
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import DocumentsPage, { formatSize } from "./DocumentsPage";

const DOC = { id: "/purchases/3/attachment", kind: "purchase", kind_label: "Factures d'achat", name: "edf-mars.pdf",
  date: "2026-03-02", size: 20480, mime: "application/pdf", party: "EDF", fiscal_year: { id: 7, label: "2026" },
  origin: { label: "Facture d'achat F-12", url: "/purchases/3" }, file_url: "/purchases/3/attachment", preview: true };
let calls: string[] = [];

beforeEach(() => {
  calls = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL) => {
    calls.push(String(input));
    return Promise.resolve(new Response(JSON.stringify({ items: [DOC], total: 1, page: 1, page_size: 50, facets: {
      kinds: [{ value: "purchase", label: "Factures d'achat", icon: "receipt", pictogram: null, count: 1 },
        { value: "coop_statement", label: "Décomptes de coopérative", icon: "scroll-text", pictogram: "barn", count: 2 }],
      fiscal_years: [{ value: "7", label: "2026", count: 1 }] } }), { status: 200 }));
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

it("liste, filtre par type et aperçu", async () => {
  renderWithProviders(<DocumentsPage />, { route: "/documents/" });
  expect(await screen.findByText("Facture d'achat F-12")).toHaveAttribute("href", "/purchases/3");
  expect(document.querySelector("[data-pictogram=barn]")).not.toBeNull();
  await userEvent.click(screen.getByText("Décomptes de coopérative"));
  await vi.waitFor(() => expect(calls.at(-1)).toContain("kind=coop_statement"));
  await userEvent.click(screen.getByRole("button", { name: "edf-mars.pdf" }));
  const drawer = await screen.findByRole("dialog");
  expect(within(drawer).getByTitle("Aperçu de edf-mars.pdf")).toHaveAttribute("src", "/purchases/3/attachment");
  expect(within(drawer).getByRole("link", { name: "Télécharger" })).toHaveAttribute("download", "edf-mars.pdf");
});

it("tailles lisibles", () => {
  expect(formatSize(512)).toBe("512 o");
  expect(formatSize(20480)).toBe("20 Ko");
  expect(formatSize(null)).toBe("");
});
