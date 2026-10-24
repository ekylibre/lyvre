// Lot F5 : dotations aux amortissements de l'exercice dans l'assistant de clôture.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders } from "../../test/render";
import { DepreciationPanel } from "./DepreciationPanel";

let posted = false;
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

beforeEach(() => {
  posted = false;
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((_input: RequestInfo | URL, init: RequestInit = {}) => {
    if ((init.method ?? "GET") === "POST") { posted = true; return json(200, { items: [], notices: [] }); }
    return json(200, { enabled: true, entry: null, items: [{ asset_id: 4, label: "Perceuse", account_code: "2154",
      depreciation_account_code: "28154", days: 286, amount_cents: 28600, posted: false }] });
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("dotations", () => {
  it("liste et passe les dotations", async () => {
    renderWithProviders(<DepreciationPanel fyId={1} editable />);
    expect(await screen.findByText("2154 / 28154")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Passer les dotations" }));
    await vi.waitFor(() => expect(posted).toBe(true));
  });
});
