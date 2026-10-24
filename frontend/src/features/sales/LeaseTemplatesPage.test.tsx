// Lot L2 : modèles de bail — onglet par type, bandeau « à relire », enregistrement, rétablissement.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders } from "../../test/render";
import LeaseTemplatesPage from "./LeaseTemplatesPage";

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
let current: typeof TEMPLATE;
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const TEMPLATE: { kind: string; title: string; version: number; reviewed: boolean; updated_at: string | null; body_html: string } = { kind: "derogatory", title: "Bail dérogatoire commercial", version: 1, reviewed: false, updated_at: null,
  body_html: "<h1>BAIL</h1><p>{{ preneur.nom }}</p>" };

beforeEach(() => {
  calls = [];
  current = TEMPLATE;
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    calls.push({ method, url, body: init.body ? JSON.parse(init.body as string) : undefined });
    if (url === "/api/v1/lease-templates") return json(200, {
      items: [current, { ...TEMPLATE, kind: "residential", title: "Bail d'habitation", reviewed: true }],
      meta: { fields: [{ value: "{{ loyer.annuel }}", label: "Loyer annuel" }], leases: [{ value: "3", label: "La Vauzelle", kind: "derogatory" }] } });
    if (url === "/api/v1/lease-templates/derogatory" && method === "GET") return json(200, { item: current });
    if (url === "/api/v1/lease-templates/derogatory" && method === "PUT") {
      current = { ...TEMPLATE, version: 2, reviewed: true, body_html: calls.at(-1)?.body.body_html };
      return json(200, { item: current, notices: [] });
    }
    return json(404, {});
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("modèles de bail", () => {
  it("modèle livré signalé, modifié en source puis enregistré", async () => {
    const user = userEvent.setup();
    renderWithProviders(<LeaseTemplatesPage />);
    expect(await screen.findByText("Modèle livré, à relire")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Bail dérogatoire commercial · à relire" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Bail d'habitation" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Enregistrer" })).toHaveProperty("disabled", true);

    await user.click(screen.getByText("Source HTML"));
    const source = screen.getByLabelText("Source du modèle Bail dérogatoire commercial");
    await user.clear(source);
    await user.click(source);
    await user.paste("<h1>BAIL</h1><p>{{ preneur.nom }} — {{ loyer.annuel }}</p>");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      body_html: "<h1>BAIL</h1><p>{{ preneur.nom }} — {{ loyer.annuel }}</p>" }));
    await waitFor(() => expect(screen.queryByText("Modèle livré, à relire")).toBeNull());
  });
});
