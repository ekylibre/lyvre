// Lot AG3.c : aides à recevoir à la clôture.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { AidAccrualPanel, type AidAccruals } from "./AidAccrualPanel";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const DATA: AidAccruals = {
  enabled: true,
  issues: [{ aid_id: 3, label: "Calamités 2026", message: "Date de la décision d'attribution à saisir." }],
  items: [{ key: "aid:1", aid_id: 1, kind: "accrued", kind_label: "Aide à recevoir", label: "Aide de base 2026",
    account_code: "7451", counterpart: "441", trigger_on: "2026-05-18", trigger_provisional: false, acquired_cents: 1800000,
    paid_cents: 1200000, amount_cents: 600000, posted: false, posted_cents: null, entry: null, dismissed: false, reason: null, mixed: false }],
};

afterEach(() => vi.restoreAllMocks());

describe("Aides à la clôture", () => {
  it("propose le produit à recevoir et exige un motif pour un autre montant", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ ...DATA, notices: [] })) as typeof globalThis.fetch);
    renderWithProviders(<AidAccrualPanel fyId={7} editable />,
      { session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByText("441 / 7451")).toBeInTheDocument();
    expect(screen.getByText(/Date de la décision d'attribution à saisir/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Retenir Aide de base 2026" }));
    const amount = screen.getByRole("textbox", { name: "Montant Aide de base 2026" });
    await userEvent.clear(amount);
    await userEvent.type(amount, "5000");
    expect(screen.getByRole("textbox", { name: "Motif Aide de base 2026" })).toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox", { name: "Motif Aide de base 2026" }), "Notifié 17 000 €");
    await userEvent.click(screen.getByRole("button", { name: "Passer les écritures (1)" }));
    await waitFor(() => expect(spy.mock.calls.some(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toBe(true));
    const [, init] = spy.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "POST")!;
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ items: [{ key: "aid:1", amount_cents: 500000, reason: "Notifié 17 000 €" }] });
  });

  it("rien hors exploitation agricole", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((() => json({ items: [], issues: [], enabled: false })) as typeof fetch);
    const { container } = renderWithProviders(<AidAccrualPanel fyId={7} editable />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(container.textContent).not.toContain("Aides et subventions");
  });
});
