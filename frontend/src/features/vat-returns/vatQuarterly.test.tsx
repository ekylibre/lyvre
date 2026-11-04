// Lot AG2.a : CA3 trimestrielle (libellé du trimestre) et remboursement de crédit demandé (3519).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import VatReturnPage from "./VatReturnPage";
import { monthLabel, type VatReturnPreview } from "./types";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const PREVIEW: VatReturnPreview = {
  period: "2026-T1", form_year: 2026, deadline: "2026-05-05", credit_carried_cents: 0, due_cents: 0, credit_cents: 180000,
  lines_count: 2, vat_return: null, codes: {}, checks: [], rows: [],
  refund: { minimum_cents: 76000, maximum_cents: 180000, possible: true },
};

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation((() => json(PREVIEW)) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("CA3 trimestrielle", () => {
  it("libellés des périodes", () => {
    expect(monthLabel("2026-T1")).toBe("1er trimestre 2026");
    expect(monthLabel("2026-T3")).toBe("3e trimestre 2026");
    expect(monthLabel("2026-07")).toBe("juillet 2026");
    expect(monthLabel("2026-A")).toBe("année 2026");
    expect(monthLabel("2025-07-A")).toBe("exercice ouvert en juillet 2025");
  });

  it("propose le remboursement du crédit", async () => {
    renderWithProviders(<Routes><Route path="/vat-returns/:period" element={<VatReturnPage />} /></Routes>,
      { route: "/vat-returns/2026-T1", session: { ...TEST_SESSION, role: "admin", permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText(/1er trimestre 2026/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Remboursement de crédit à demander/)).toBeInTheDocument();
    expect(screen.getByText(/De 760 € à 1\s800 €/)).toBeInTheDocument();
  });
});
