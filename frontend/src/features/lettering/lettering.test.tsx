// Lot F3 : écran de lettrage (sélection au clavier, total, lettrage, propositions).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders } from "../../test/render";
import LetteringPage from "./LetteringPage";

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const line = (id: number, ref: string, debit: number, credit: number) => ({ id, entry_id: id, reference: ref, journal: "VE",
  date: "2026-03-01", label: ref, debit_cents: debit, credit_cents: credit, carried: false, lettering: null });

beforeEach(() => {
  calls = [];
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    calls.push({ method: init.method ?? "GET", url, body: init.body ? JSON.parse(init.body as string) : undefined });
    if (url === "/api/v1/lettering/accounts") return json(200, { items: [{ id: 7, code: "411001", label: "Client SARL", open_lines: 3, open_balance_cents: 5000 }], gap_threshold_cents: 100 });
    if (url.startsWith("/api/v1/lettering/accounts/7/lines")) return json(200, { account: { id: 7, code: "411001", label: "Client SARL" },
      open_balance_cents: 5000, items: [line(1, "VE-1", 12000, 0), line(2, "BQ-1", 0, 12000), line(3, "VE-2", 5000, 0)] });
    if (url === "/api/v1/lettering/accounts/7/proposals") return json(200, { items: [{ kind: "pair", line_ids: [1, 2], amount_cents: 12000 }] });
    if (url === "/api/v1/lettering") return json(201, { item: { id: 1, code: "A", partial: false }, notices: [] });
    return json(404, {});
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("lettrage", () => {
  it("sélection au clavier, solde, lettrage par Entrée", async () => {
    renderWithProviders(<LetteringPage />, { route: "/lettering/" });
    const row = (await screen.findByText("VE-1", { selector: "a" })).closest("tr")!;
    row.focus();
    await userEvent.keyboard(" ");
    await userEvent.keyboard("{ArrowDown}");
    await userEvent.keyboard(" ");
    expect(await screen.findByText(/2 ligne\(s\)/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Lettrer (Entrée)" })).toBeTruthy();
    await userEvent.keyboard("{Enter}");
    await vi.waitFor(() => expect(calls.find((c) => c.url === "/api/v1/lettering")?.body).toEqual({ line_ids: [1, 2], gap: false }));
  });

  it("proposition acceptée", async () => {
    renderWithProviders(<LetteringPage />, { route: "/lettering/" });
    const panel = (await screen.findByText("Propositions (1)")).closest("div")!.parentElement!;
    await userEvent.click(within(panel).getByRole("button", { name: "Accepter" }));
    await vi.waitFor(() => expect(calls.find((c) => c.url === "/api/v1/lettering")?.body).toEqual({ line_ids: [1, 2], proposal: true }));
  });
});
