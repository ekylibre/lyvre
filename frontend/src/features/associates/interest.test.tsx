import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import { InterestPanel } from "./InterestPanel";

const ADMIN = { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } };
let posted = 0;
const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status: 200 }));

beforeEach(() => {
  posted = 0;
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    if ((init.method ?? "GET") === "POST") { posted += 1; return json({ notices: [] }); }
    void input;
    return json({ total_cents: 200000, entries: [], rows: [
      { associate_id: 1, name: "Prêteur", account_code: "4551001", rate: "2", average_balance_cents: 10000000, interest_cents: 200000 }] });
  }) as typeof fetch);
});

afterEach(() => vi.restoreAllMocks());

describe("intérêts des comptes courants", () => {
  it("aperçu puis écritures, par l'administrateur sur un exercice ouvert", async () => {
    const user = userEvent.setup();
    renderWithProviders(<InterestPanel fyId={3} open />, { session: ADMIN });
    expect(await screen.findByText("Prêteur")).toBeTruthy();
    expect(screen.getByText("2 %")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: /Passer les intérêts/ }));
    await waitFor(() => expect(posted).toBe(1));
  });

  it("exercice clôturé : lecture seule", async () => {
    renderWithProviders(<InterestPanel fyId={3} open={false} />, { session: ADMIN });
    expect(await screen.findByText("Prêteur")).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });
});
