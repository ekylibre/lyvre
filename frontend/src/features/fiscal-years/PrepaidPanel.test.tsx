// Lot F4 : propositions de charges constatées d'avance à la clôture.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders } from "../../test/render";
import { PrepaidPanel } from "./PrepaidPanel";

let posted: unknown;
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const ITEM = { key: "prepaid_expense:purchase:3:6161", kind: "prepaid_expense", source: "purchase", url: "/purchases/3",
  label: "Assureur A-1", account_code: "6161", period_start: "2026-07-01", period_end: "2027-06-30", base_cents: 120000,
  days_after: 181, days_total: 365, amount_cents: 59507, posted: false };

beforeEach(() => {
  posted = undefined;
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    if ((init.method ?? "GET") === "POST") { posted = JSON.parse(init.body as string); return json(200, { items: [], notices: [] }); }
    if (String(input) === "/api/v1/fiscal-years/1/closing/prepaid") return json(200, { items: [ITEM] });
    return json(404, {});
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("charges constatées d'avance", () => {
  it("proposition retenue puis passée", async () => {
    renderWithProviders(<PrepaidPanel fyId={1} editable />);
    expect(await screen.findByText("181 / 365 jours après la clôture")).toBeTruthy();
    await userEvent.click(screen.getByLabelText("Retenir Assureur A-1"));
    await userEvent.click(screen.getByRole("button", { name: "Passer les écritures (1)" }));
    await vi.waitFor(() => expect(posted).toEqual({ items: [{ key: ITEM.key, amount_cents: 59507 }] }));
  });
});
