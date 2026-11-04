// Lot AG3.e : montants publiés par l'ASP.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { CapCheckCard, type CapCheck } from "./CapCheckCard";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const CHECK: CapCheck = {
  year: 2025, configured: true, siren: "123456782", years: [2025, 2024], fetched_at: "2026-11-05T08:00:00", found: true,
  paid_cents: 1500000, ledger_cents: 1500000, message: null,
  published: { feaga_cents: 1850050, feader_cents: 120000, cofinanced_cents: 30000, total_cents: 2000050 },
  gap_paid_cents: -500050, gap_ledger_cents: -500050,
};

afterEach(() => vi.restoreAllMocks());

describe("Montants publiés par l'ASP", () => {
  it("compare le publié aux versements et aux comptes", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ item: CHECK })) as typeof globalThis.fetch);
    renderWithProviders(<CapCheckCard year={2025} />,
      { session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("Montants publiés par l'ASP — 2025")).toBeInTheDocument();
    expect(screen.getByText(/Versements rattachés en 2025/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Relire dans Lexicon" })).toBeInTheDocument();
  });

  it("masquée sans Lexicon configuré", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation((() =>
      json({ item: { ...CHECK, configured: false, published: null } })) as typeof globalThis.fetch);
    const { container } = renderWithProviders(<CapCheckCard year={2025} />);
    await vi.waitFor(() => expect(spy).toHaveBeenCalled());
    expect(container.textContent).not.toContain("Montants publiés");
  });
});
