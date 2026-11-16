// Lot AG3.d : subventions d'investissement (reprise à la clôture, fiche du dossier).
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { GrantReleasePanel, type GrantReleases } from "./GrantReleasePanel";
import { InvestmentSection } from "./InvestmentSection";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const admin = { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } };
const DATA: GrantReleases = {
  enabled: true, entry: null,
  items: [{ aid_id: 1, aid_label: "PCAE 2026", asset_id: 4, asset_label: "Stabulation", kind: "depreciation", amount_cents: 100000,
    dotation_cents: 500000, base_cents: 5000000, posted: false, release_id: null, reason: null }],
  annex: [{ aid_id: 1, label: "PCAE 2026", account_code: "131", amount_cents: 1000000, released_before_cents: 0,
    released_cents: 100000, remaining_cents: 900000, assigned_cents: 1000000, granted: true }],
};

afterEach(() => vi.restoreAllMocks());

describe("Subventions d'investissement", () => {
  it("reprise calculée et annexe à la clôture", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json(DATA)) as typeof globalThis.fetch);
    renderWithProviders(<GrantReleasePanel fyId={3} editable />, { session: admin });
    expect(await screen.findByText("Stabulation")).toBeInTheDocument();
    expect(screen.getByText(/au rythme de l'amortissement/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Passer la reprise" })).toBeEnabled();
    expect(screen.getByText("Subventions d'investissement (annexe)")).toBeInTheDocument();
  });

  it("octroi proposé avant le premier versement", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ items: [] })) as typeof globalThis.fetch);
    renderWithProviders(<InvestmentSection aidId={1} hasPayments={false} invalidate={[]}
      investment={{ amount_cents: 1000000, released_cents: 0, grant_entry: null, assets: [] }} />, { session: admin });
    expect(screen.getByRole("button", { name: "Passer l'octroi" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ajouter une immobilisation" })).toBeInTheDocument();
  });
});
