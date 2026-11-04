// Lot AG3.b : rattacher un virement reçu aux dossiers d'aide.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Aid } from "./AidsPage";
import { LinkAidModal, type AidCandidates } from "./LinkAidModal";

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));
const aid = (id: number, label: string, code: string, remaining: number, payer = "ASP"): Aid => ({
  id, scheme: "basic_income", scheme_label: label, label, campaign: 2026, payer, nature: "operating", nature_label: "",
  account: { id, code, label }, operating_account: null, investment_share_cents: null, trigger: "pac_deadline",
  trigger_label: "", trigger_on: null, trigger_provisional: false, decision_on: null, requested_cents: remaining,
  notified_cents: null, notified_on: null, acquired_cents: remaining, paid_cents: 0, remaining_cents: remaining,
  payment_request_deadline: null, payment_requested_on: null, commitment_end_on: null, status: "requested",
  status_label: "Demandée", notes: null, warnings: [],
});
const CANDIDATES: AidCandidates = {
  transaction: { id: 5, label: "VIR ASP PAC", counterparty: null, transaction_date: "2026-10-16", amount_cents: 921018,
    booked: false, booked_accounts: [] },
  payer: "ASP", allocated_cents: 0, free_cents: 921018,
  items: [{ aid: aid(1, "Aide de base", "7451", 800000), payer_match: true, suggested_cents: 800000, already_linked: false },
    { aid: aid(2, "Écorégime", "7453", 200000), payer_match: true, suggested_cents: 200000, already_linked: false }],
};

afterEach(() => vi.restoreAllMocks());

describe("Rattacher à une aide", () => {
  it("propose le premier dossier du payeur, ventile et comptabilise", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(((url: string) =>
      json(String(url).includes("candidates") ? { item: CANDIDATES } : { item: { booked: true, warnings: [] }, notices: [] })) as typeof fetch);
    renderWithProviders(<LinkAidModal txId={5} onClose={() => undefined} />,
      { session: { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } } });
    expect(await screen.findByRole("checkbox", { name: "Rattacher à Aide de base 2026" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Rattacher à Écorégime 2026" })).not.toBeChecked();
    expect(screen.getByText(/payeur reconnu : ASP/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: "Rattacher à Écorégime 2026" }));
    expect(screen.getByRole("checkbox", { name: /Comptabiliser le virement/ })).toBeChecked();
    expect(screen.getByText(/Ventilez la totalité/)).toBeInTheDocument();          // 10 000 € > 9 210,18 €
    expect(screen.getByRole("button", { name: "Rattacher" })).toBeDisabled();
    const amount = screen.getByRole("textbox", { name: "Montant pour Aide de base" });
    await userEvent.clear(amount);
    await userEvent.type(amount, "7210,18");
    await userEvent.click(screen.getByRole("button", { name: "Rattacher" }));
    await waitFor(() => expect(fetch.mock.calls.some(([u]) => String(u).endsWith("/aids/link"))).toBe(true));
    const [, init] = fetch.mock.calls.find(([u]) => String(u).endsWith("/aids/link"))!;
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ bank_transaction_id: 5, book: true, allocations: [
      { aid_id: 1, amount_cents: 721018, kind: "advance" }, { aid_id: 2, amount_cents: 200000, kind: "balance" }] });
  });
});
