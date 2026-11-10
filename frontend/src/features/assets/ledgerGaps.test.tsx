// Essai de l'interface (10/11/2026) : immobilisations comptabilisées sans fiche.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { draftFrom, LedgerGapsCard, type LedgerGap } from "./LedgerGapsCard";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const base = { register_cents: 0, prior_as_of: "2024-01-31", depreciation_accounts: [] as string[], shared_with: [] as string[] };
const GAPS: LedgerGap[] = [
  { ...base, account: { id: 1, code: "2154", label: "Matériels industriels" }, ledger_cents: 102681240, gap_cents: 102681240,
    depreciation_cents: 71925372, opening_depreciation_cents: 70732252, depreciation_accounts: ["2815"], no_depreciation: false },
  { ...base, account: { id: 2, code: "213", label: "Constructions" }, ledger_cents: 123850489, gap_cents: 123850489,
    depreciation_cents: 140949841, opening_depreciation_cents: 131340676, depreciation_accounts: ["2813"], shared_with: ["2135"], no_depreciation: false },
  { ...base, account: { id: 3, code: "241", label: "Animaux reproducteurs" }, ledger_cents: 5029639, gap_cents: 5029639,
    depreciation_cents: 0, opening_depreciation_cents: 0, no_depreciation: true },
];

afterEach(() => vi.restoreAllMocks());

describe("Immobilisations comptabilisées sans fiche", () => {
  it("préremplit la fiche ; amortissements communs non repris", () => {
    expect(draftFrom(GAPS[0])).toMatchObject({ account_id: "1", acquisition_cents: 102681240, prior_depreciation_cents: 70732252, prior_as_of: "2024-01-31" });
    expect(draftFrom(GAPS[1]).prior_depreciation_cents).toBe(0);
  });

  it("liste les écarts, signale le compte sans amortissement et ouvre la fiche", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ items: GAPS, fiscal_year: { label: "2024-2025", end_date: "2025-01-31" } })) as typeof fetch);
    const onCreate = vi.fn();
    renderWithProviders(<LedgerGapsCard canWrite onCreate={onCreate} />);
    expect(await screen.findByText("Immobilisations comptabilisées sans fiche")).toBeInTheDocument();
    expect(screen.getByText("sans amortissement")).toBeInTheDocument();
    expect(screen.getByText(/commun avec 2135/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Créer la fiche" })[2]);
    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ account_id: "3", acquisition_cents: 5029639 }));
  });
});
