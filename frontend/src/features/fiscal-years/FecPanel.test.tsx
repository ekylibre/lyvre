// Panneau FEC : l'archive pour l'expert-comptable (lot RQ4) reste proposée quand le FEC ne peut pas être produit,
// et pas dans l'essai à blanc de l'assistant de clôture.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import { FecPanel, type FecCheck } from "./FecPanel";

const CHECK: FecCheck = {
  errors: ["L'exercice doit être au moins en clôture provisoire."], warnings: [], problems: [], filename: null,
  frozen: false, sha256: null, download_url: null, stats: null,
};

beforeEach(() => {
  vi.spyOn(globalThis, "fetch").mockImplementation((() =>
    Promise.resolve(new Response(JSON.stringify(CHECK), { status: 200 }))) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("panneau FEC", () => {
  it("propose l'archive pour l'expert-comptable même sans FEC", async () => {
    renderWithProviders(<FecPanel fiscalYearId={3} />);
    const link = await screen.findByRole("link", { name: /Archive pour l'expert-comptable/ });
    expect(link).toHaveAttribute("href", "/fiscal-years/3/accountant-archive.zip");
    expect(screen.getByText(/s'il peut être produit/)).toBeInTheDocument();
  });

  it("pas d'archive dans l'essai à blanc", async () => {
    renderWithProviders(<FecPanel fiscalYearId={3} preview />);
    await screen.findByText("Le FEC ne peut pas encore être produit");
    expect(screen.queryByRole("link", { name: /Archive/ })).not.toBeInTheDocument();
  });
});
