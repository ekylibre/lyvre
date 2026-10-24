// Lot L5 : indices de loyer — valeurs par indice, mise à jour INSEE, saisie de l'indice des fermages.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders } from "../../test/render";
import RentIndicesPage from "./RentIndicesPage";

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

beforeEach(() => {
  calls = [];
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    calls.push({ method, url, body: init.body ? JSON.parse(init.body as string) : undefined });
    if (url === "/api/v1/rent-indices" && method === "GET") return json(200, {
      items: [{ id: 1, code: "ILC", period: "2026-Q2", period_label: "2e trimestre 2026", value: "137.16", source: "insee", fetched_at: "2026-10-25T08:00:00" }],
      meta: { indexes: [{ value: "ILC", label: "Indice des loyers commerciaux (ILC)" }, { value: "FERMAGES", label: "Indice national des fermages" }],
        insee: ["ILAT", "ILC", "IRL"], last_fetch: "2026-10-25T08:00:00" } });
    if (url === "/api/v1/rent-indices" && method === "POST") return json(201, { item: {}, notices: [] });
    if (url === "/api/v1/rent-indices/fetch") return json(200, { notices: [] });
    return json(404, {});
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("indices de loyer", () => {
  it("liste, mise à jour INSEE et saisie de l'indice des fermages", async () => {
    const user = userEvent.setup();
    renderWithProviders(<RentIndicesPage />);
    expect(await screen.findByText("2e trimestre 2026")).toBeTruthy();
    expect(screen.getByText("137,16")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Mettre à jour depuis l'INSEE" }));
    await waitFor(() => expect(calls.some((c) => c.url === "/api/v1/rent-indices/fetch")).toBe(true));
    await user.type(screen.getByLabelText("Période"), "2025");
    await user.type(screen.getByLabelText("Valeur"), "123,06");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.url === "/api/v1/rent-indices")?.body)
      .toEqual({ code: "FERMAGES", period: "2025", value: "123,06" }));
  });
});
