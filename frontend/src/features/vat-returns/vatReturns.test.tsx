// Déclarations de TVA (lot T3) : fiche d'un mois (cases, contrôles, lignes d'une case) et liste des mois.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { renderWithProviders } from "../../test/render";
import VatReturnPage from "./VatReturnPage";
import VatReturnsPage from "./VatReturnsPage";
import type { VatReturnPreview } from "./types";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));

const PREVIEW: VatReturnPreview = {
  period: "2026-08", form_year: 2026, deadline: "2026-09-24", credit_carried_cents: 10000, due_cents: 28000,
  credit_cents: 0, lines_count: 3, vat_return: null, codes: { V20: { base: 190199, tax: 38040, deductible: 0 } },
  checks: [{ level: "error", message: "Validez d'abord la déclaration de 07/2026 : son crédit se reporte sur ce mois.", count: null }],
  rows: [
    { kind: "section", label: "B — Décompte de la TVA à payer : TVA brute" },
    { kind: "box", line: "08", code: "0207", label: "Taux normal 20 %", with_base: true, base: 1902, amount: 380,
      note: "dont 18,00 € de TVA autoliquidée, déduite ligne 20" },
    { kind: "total", line: "16", code: null, label: "Total de la TVA brute due", with_base: false, base: null, amount: 380 },
  ],
};

let urls: string[];
beforeEach(() => {
  urls = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL) => {
    const url = String(input);
    urls.push(url);
    if (url.startsWith("/api/v1/vat-returns/preview")) return json(PREVIEW);
    if (url.startsWith("/api/v1/vat-returns/lines")) return json({ items: [{ id: 1, entry_id: 9, reference: "OD-2026-0009",
      date: "2026-08-05", description: "Vente", account: "44571", label: "TVA", debit_cents: 0, credit_cents: 40040,
      vat_code: "V20", vat_base_cents: 200199 }] });
    if (url.startsWith("/api/v1/vat-returns")) return json({ fiscal_year: { id: 1, label: "2026-2027" },
      fiscal_years: [{ value: "1", label: "2026-2027" }], items: [
        { period: "2026-07", start: "2026-07-01", end: "2026-07-31", deadline: "2026-08-24", late: true,
          status: "to_prepare", status_label: "À préparer", return: null }] });
    return json({ items: [] });
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("déclaration d'un mois", () => {
  it("contrôle bloquant : validation impossible ; une case ouvre ses lignes", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Routes><Route path="/vat-returns/:period" element={<VatReturnPage />} /></Routes>,
      { route: "/vat-returns/2026-08" });
    expect(await screen.findByRole("alert")).toHaveTextContent("07/2026");
    expect(screen.getByRole("button", { name: "Valider" })).toBeDisabled();
    expect(screen.getByText(/TVA nette due/)).toBeInTheDocument();
    expect(screen.getByText("dont 18,00 € de TVA autoliquidée, déduite ligne 20")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Lignes de la case 08" }));
    expect(await screen.findByText("OD-2026-0009")).toBeInTheDocument();
    expect(urls.some((u) => u.includes("box=08"))).toBe(true);
  });
});

describe("liste des mois", () => {
  it("signale les déclarations en retard", async () => {
    renderWithProviders(<VatReturnsPage />, { route: "/vat-returns/" });
    expect(await screen.findByText(/1 déclaration en retard/)).toBeInTheDocument();
    expect(screen.getByText("À préparer — en retard")).toBeInTheDocument();
  });
});
