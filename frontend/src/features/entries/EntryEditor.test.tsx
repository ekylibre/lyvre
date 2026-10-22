import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/render";
import { EntryEditor, type EntryFormData } from "./EntryEditor";

const BANK = { id: 1, code: "512000", label: "Banque" };
const EXPENSE = { id: 2, code: "606300", label: "Petit équipement" };

const DATA: EntryFormData = {
  mode: "create",
  options: {
    fiscalYears: [{ id: 1, label: "2026", start_date: "2026-01-01", end_date: "2026-12-31" }],
    journals: [{ id: 1, code: "AC", label: "Achats" }], recentsScope: "test",
  },
  initial: { fiscal_year_id: 1, journal_id: 1, entry_date: "2026-03-02", description: "Perceuse",
    lines: [{ account: EXPENSE, debit_cents: 8990 }, { account: BANK }] },
};

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => vi.restoreAllMocks());

describe("EntryEditor", () => {
  it("équilibre avec « = » puis enregistre et repart d'une saisie vide (Ctrl+Entrée)", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (url) =>
      String(url).endsWith("/validate") ? json({ errors: {} })
        : json({ id: 7, reference: "AC-2026-0007", url: "/entries/7", reconciled: false, editable: true }, 201));
    const onSaved = vi.fn();
    renderWithProviders(<EntryEditor data={DATA} onSaved={onSaved} onCancel={() => {}} />);

    expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
    const credit = screen.getByLabelText("Crédit, ligne 2");
    await userEvent.click(credit);
    await userEvent.keyboard("=");
    expect(credit).toHaveValue("89,90");
    expect(screen.getByText(/Équilibrée : 89,90/)).toBeInTheDocument();

    await userEvent.keyboard("{Control>}{Enter}{/Control}");
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }), "continue"));
    const post = fetchMock.mock.calls.find(([u, init]) => String(u) === "/api/v1/entries" && init?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body)).lines.map((l: { debit_cents: number; credit_cents: number }) =>
      [l.debit_cents, l.credit_cents])).toEqual([[8990, 0], [0, 8990]]);
    // Saisie suivante : description et lignes vidées, exercice et journal gardés.
    await waitFor(() => expect(screen.getByLabelText("Description")).toHaveValue(""));
    expect(screen.getByLabelText("Débit, ligne 1")).toHaveValue("");
  });

  it("signale l'écart et une date hors exercice", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ errors: {} }));
    renderWithProviders(<EntryEditor data={{ ...DATA, initial: { ...DATA.initial, entry_date: "2025-12-31" } }}
      onSaved={() => {}} onCancel={() => {}} />);
    expect(screen.getByText("Écart : 89,90 €")).toBeInTheDocument();
    expect(screen.getByText("Hors de l'exercice 2026.")).toBeInTheDocument();
  });
});
