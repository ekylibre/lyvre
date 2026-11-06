// Lot AG10.c : autofactures reçues (contrôles, compte par ligne) et cycle de vie (contestation).
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { LifecycleForm } from "./SaleDetailPage";
import { SelfBilledReview, type SelfBilledAnalysis } from "./SelfBilledPage";
import type { SaleDetail } from "./types";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
afterEach(() => vi.restoreAllMocks());

const ANALYSIS: SelfBilledAnalysis = {
  syntax: "cii", container: "pdf", type_code: "389", self_billed: true, number: "AF-2026-0042", issue_date: "2026-10-15",
  due_date: "2026-11-15", seller: { name: "EARL des Essais", siren: "552100554", vat_number: null, city: null },
  buyer: { name: "Coopérative Fictive", siren: "775665912", vat_number: null, city: "La Rochelle" }, client: null,
  lines: [
    { index: 0, label: "MAIS GRAINS", kind: "line", quantity: "12.5", unit: "t", unit_price: "180", net_cents: 225000, vat_rate_bp: 550,
      account_code: "7011001", account_origin: "activité" },
    { index: 1, label: "Frais de collecte", kind: "allowance", quantity: "1", unit: "", unit_price: "", net_cents: -5000, vat_rate_bp: 550,
      account_code: "", account_origin: null },
  ],
  taxes: [{ rate_bp: 550, base_cents: 220000, tax_cents: 12100 }], untaxed_cents: 220000, tax_cents: 12100, total_cents: 232100,
  payable_cents: 232100, notes: [], problems: [], warnings: ["TVA à 5,5 % : 121,00 € facturés pour 120,00 € calculés."],
};

describe("Autofactures reçues", () => {
  it("affiche les contrôles, les lignes et le compte proposé", () => {
    const onAccount = vi.fn();
    renderWithProviders(<SelfBilledReview analysis={ANALYSIS} accounts={{ 0: "7011001", 1: "" }}
      options={[{ value: "7011001", label: "7011001 — Maïs grain" }]} onAccount={onAccount} />);
    expect(screen.getByText("AF-2026-0042")).toBeInTheDocument();
    expect(screen.getByText(/autofacture \(389\)/)).toBeInTheDocument();
    expect(screen.getByText("fiche créée à l'enregistrement · SIREN 775665912")).toBeInTheDocument();
    expect(screen.getByText("proposé : activité")).toBeInTheDocument();
    expect(screen.getByText("remise")).toBeInTheDocument();
    expect(screen.getByText(/121,00 € facturés/)).toBeInTheDocument();
  });

  it("refuse l'enregistrement d'une autofacture en erreur", () => {
    renderWithProviders(<SelfBilledReview analysis={{ ...ANALYSIS, problems: ["Doublon : déjà enregistrée."] }} accounts={{}}
      options={[]} onAccount={vi.fn()} />);
    expect(screen.getByText("Autofacture refusée :")).toBeInTheDocument();
    expect(screen.getByText("Doublon : déjà enregistrée.")).toBeInTheDocument();
  });

  it("conteste avec un motif", async () => {
    const sale = { id: 5, number: "AF-2026-0042", lines: [] } as unknown as SaleDetail;
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ item: sale, notices: [] })) as typeof fetch);
    const onDone = vi.fn();
    renderWithProviders(<LifecycleForm sale={sale} status="disputed" onDone={onDone} />);
    expect(screen.getByText(/en litige » \(fr:207\)/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/Motif/), "Poids erroné");
    await userEvent.click(screen.getByRole("button", { name: "Contester" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    const [url, init] = spy.mock.calls[0];
    expect(url).toBe("/api/v1/sales/5/lifecycle");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ status: "disputed", reason: "Poids erroné", accounts: {} });
  });
});
