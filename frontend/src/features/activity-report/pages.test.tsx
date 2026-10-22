import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import EcoPage from "./EcoPage";
import TextsPage from "./TextsPage";

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const ADMIN = { ...TEST_SESSION, user: { ...TEST_SESSION.user!, is_admin: true } };
// HTML que l'éditeur réécrirait (div → p) : il doit repartir tel quel s'il n'est pas modifié.
const RAW = '<div class="encadre"><p>Bonjour <span style="color:red">à tous</span></p></div>';

beforeEach(() => {
  calls = [];
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    calls.push({ method, url, body: init.body ? JSON.parse(init.body as string) : undefined });
    if (url.startsWith("/api/v1/activity-report/texts") && method === "GET") {
      return json(200, { fiscal_year: { id: 3, label: "2025" }, site: { available: false, preview: [] },
        blocks: [{ key: "edito", label: "Édito", title: "Le mot", body: RAW }, { key: "bilan", label: "Bilan", title: "", body: "" }] });
    }
    if (url.startsWith("/api/v1/activity-report?") || url === "/api/v1/activity-report") {
      return json(200, { fiscal_years: [{ value: "3", label: "2025" }], fiscal_year: { id: 3, label: "2025" }, prorata: false,
        links: { preview: "/p", pdf: "/pdf", html: "/h", docx: "/d", odt: "/o" } });
    }
    if (url === "/api/v1/activity-report/eco" && method === "GET") {
      return json(200, { items: [
        { id: 1, organism: "Ecomaison", material: "Meubles", quarter: "T2 2025", entrant_t: 10, sortant_t: 4, financing_cents: 100000, source: "import" },
        { id: 2, organism: "Ecologic", material: "D3E", quarter: "T2 2025", entrant_t: 2, sortant_t: 1, financing_cents: 10000, source: "import" },
      ] });
    }
    if (method === "PUT") return json(200, { notices: [] });
    return json(404, { error: { code: "not_found", message: "?" } });
  }) as typeof fetch);
});

afterEach(() => vi.restoreAllMocks());

describe("rapport d'activité", () => {
  it("renvoie le HTML d'un bloc non modifié tel quel", async () => {
    const user = userEvent.setup();
    renderWithProviders(<TextsPage />, { session: ADMIN, route: "/rapport-activite/edit" });
    await user.click(await screen.findByRole("button", { name: "Enregistrer" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.url).toBe("/api/v1/activity-report/texts");
    expect(put.body).toEqual({ fy_id: 3, blocks: [
      { key: "edito", label: "Édito", title: "Le mot", body: RAW }, { key: "bilan", label: "Bilan", title: "", body: "" }] });
  });

  it("n'envoie que les tonnages modifiés ou supprimés", async () => {
    const user = userEvent.setup();
    renderWithProviders(<EcoPage />, { session: ADMIN, route: "/rapport-activite/eco" });
    const entrant = await screen.findByLabelText("Entrant Ecomaison Meubles T2 2025");
    expect(screen.getByRole("button", { name: "Enregistrer" })).toHaveProperty("disabled", true);
    await user.clear(entrant);
    await user.type(entrant, "12,5");
    await user.click(screen.getByLabelText("Supprimer Ecologic D3E T2 2025"));
    await user.click(screen.getByRole("button", { name: "Enregistrer (2)" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    const rows = calls.find((c) => c.method === "PUT")!.body.rows;
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ id: 1, entrant_t: 12.5, sortant_t: 4, financing_cents: 100000 });
    expect(rows[1]).toMatchObject({ id: 2, delete: true });
  });
});
