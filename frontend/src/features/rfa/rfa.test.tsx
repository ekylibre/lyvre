// Lot AG2.e : écran du remboursement forfaitaire (3520).
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import RfaPage, { type RfaYear } from "./RfaPage";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const YEAR: RfaYear = {
  year: 2026, regime: "rfa", high_base_cents: 1000000, low_base_cents: 500000, excluded_cents: 100000,
  non_eligible_cents: 200000, unclassified_cents: 0, high_bp: 559, low_bp: 443, amount_cents: 78100,
  deadline: "2027-12-31", late: false, can_declare: true, problems: [], warnings: ["1 client sans attestation d'achats conforme : joignez les attestations à la demande."],
  accounts: [{ account_id: 1, code: "7011", label: "Ventes de produits végétaux", rate: "low", source: "category", total_cents: 500000 }],
  clients: [{ entity_id: 5, name: "Laiterie", buyer: "professional", buyer_guessed: true, eligible: true, high_cents: 1000000,
    low_cents: 0, excluded_cents: 100000, unclassified_cents: 0, eligible_cents: 1000000, attestation: null,
    issues: ["Attestation d'achats manquante."] }],
  threshold: { threshold_cents: 4600000, factor: 1, average_cents: 1800000, over: false, years: [{ year: 2025, receipts_cents: 0 }, { year: 2026, receipts_cents: 1800000 }] },
  rates: [{ value: "high", label: "Taux de 5,59 %" }, { value: "low", label: "Taux de 4,43 %" }, { value: "excluded", label: "Exclu" }],
  buyers: [{ value: "professional", label: "Assujetti en France" }, { value: "none", label: "Particulier" }],
  years_available: [2026, 2025], claim: null,
};

afterEach(() => vi.restoreAllMocks());

describe("Remboursement forfaitaire", () => {
  it("forfait, contrôles et attestation à saisir", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json(YEAR)) as typeof fetch);
    renderWithProviders(<RfaPage />, { route: "/rfa/?year=2026",
      session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("Attestation d'achats manquante.")).toBeInTheDocument();
    expect(screen.getByText(/sans attestation d'achats conforme/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Saisir" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Marquer déposée" })).toBeEnabled();
    expect(screen.getByText("avant le 31/12/2027")).toBeInTheDocument();
  });
});
