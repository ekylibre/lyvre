// Lot F2 : verrouillage d'une période (aperçu des brouillards validés, envoi de la date).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders } from "../../test/render";
import { LockForm } from "./PeriodLock";

let posted: unknown;
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

beforeEach(() => {
  posted = undefined;
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    if (url.startsWith("/api/v1/fiscal-years/1/period-lock?until=")) return json(200, { preview: { drafts: 4, problems: [] } });
    if (url === "/api/v1/fiscal-years/1/period-lock") { posted = JSON.parse(init.body as string); return json(200, { notices: [] }); }
    return json(404, {});
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("verrouillage", () => {
  it("annonce les brouillards validés et envoie la date", async () => {
    const done = vi.fn();
    renderWithProviders(<LockForm fy={{ id: 1, label: "2026", start_date: "2026-01-01", end_date: "2026-12-31" }} onDone={done} />);
    expect(await screen.findByText(/4 écriture\(s\) en brouillard seront validées/)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Verrouiller" }));
    await vi.waitFor(() => expect(done).toHaveBeenCalled());
    expect((posted as { until: string }).until).toMatch(/^2026-\d{2}-\d{2}$/);
  });
});
