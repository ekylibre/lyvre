// Essai de l'interface (09/11/2026) : aides comptabilisées sans dossier.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { LedgerLinesCard, type LedgerLine } from "./LedgerLinesCard";

const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const account = { id: 1, code: "745", label: "Subventions au revenu" };
const LINES: LedgerLine[] = [
  { id: 11, entry_id: 1, reference: "OD1", date: "2024-03-05", label: "Aide DPB", amount_cents: 921018, account },
  { id: 12, entry_id: 2, reference: "OD2", date: "2024-10-16", label: "Aide DPB solde", amount_cents: 1248308, account },
];

afterEach(() => vi.restoreAllMocks());

describe("Aides comptabilisées sans dossier", () => {
  it("crée un dossier depuis les écritures choisies", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) => String(url).includes("schemes")
      ? json({ items: [{ key: "basic_income", label: "Aide de base au revenu (DPB)", accounts: [{ code: "7451" }, { code: "745" }] }] })
      : json({ item: {}, notices: [] }, 201)) as typeof fetch);
    renderWithProviders(<LedgerLinesCard lines={LINES} campaign={2024} aids={[]} canWrite invalidate={[["aids"]]} />,
      { session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(screen.getByText(/Aides comptabilisées sans dossier — 2024/)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Choisir l'écriture du 05/03/2024"));
    await userEvent.click(screen.getByLabelText("Choisir l'écriture du 16/10/2024"));
    await userEvent.click(await screen.findByRole("combobox", { name: "Dispositif du nouveau dossier" }));
    await userEvent.click(await screen.findByRole("option", { name: "Aide de base au revenu (DPB)" }));
    await userEvent.click(screen.getByRole("button", { name: "Créer le dossier" }));
    const post = fetch.mock.calls.find(([url]) => String(url).includes("from-ledger"));
    expect(JSON.parse(String((post![1] as RequestInit).body))).toEqual({ scheme: "basic_income", campaign: 2024, line_ids: [11, 12] });
  });

  it("rien à afficher sans écriture", () => {
    const { container } = renderWithProviders(<LedgerLinesCard lines={[]} campaign={2024} aids={[]} canWrite={false} invalidate={[]} />);
    expect(container.textContent).not.toMatch(/sans dossier/);
  });
});
