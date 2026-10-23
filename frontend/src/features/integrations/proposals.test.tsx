// Proposer les intégrations recommandées (lot I3) : ordre et badge de la page Intégrations, encart
// du tableau de bord, cases à la création d'une instance.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Session } from "../../api/session";
import InstancesPage from "../instances/InstancesPage";
import { IntegrationProposals } from "./IntegrationProposals";
import IntegrationsPage from "./IntegrationsPage";
import { sortIntegrations, type Integration } from "./types";

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

const item = (slug: string, fields: Partial<Integration> = {}): Integration => ({
  slug, label: slug === "qonto" ? "Qonto" : slug.toUpperCase(), description: "", status: "disabled", status_label: "Désactivée",
  enabled: false, configured: false, check_outdated: false, last_check: null, recommended: false, ...fields,
});

const INSTANCES_META = {
  charts: [{ value: "asso", label: "Association" }, { value: "sci", label: "SCI" }], default_chart: "asso",
  integrations_by_chart: {
    asso: [{ value: "helloasso", label: "HelloAsso", recommended: true }, { value: "smtp", label: "SMTP (emails)", recommended: false }],
    sci: [{ value: "smtp", label: "SMTP (emails)", recommended: false }, { value: "qonto", label: "Qonto", recommended: true }],
  },
};

beforeEach(() => {
  calls = [];
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    calls.push({ method, url, body: init.body ? JSON.parse(init.body as string) : undefined });
    if (url === "/api/v1/integrations") return json(200, { items: [item("smtp"), item("qonto", { recommended: true }),
      item("odoo", { enabled: true, status: "ok", status_label: "Opérationnelle" })] });
    if (url.endsWith("/dismiss")) return json(200, { notices: [] });
    if (url === "/api/v1/instances" && method === "GET") return json(200, { items: [], meta: INSTANCES_META });
    if (url === "/api/v1/users") return json(200, { items: [], meta: { roles: [] } });
    if (url === "/api/v1/instances" && method === "POST") return json(201, { item: {}, notices: [] });
    return json(404, { error: { code: "not_found", message: "?" } });
  }) as typeof fetch);
});

afterEach(() => vi.restoreAllMocks());

const ADMIN: Session = { ...TEST_SESSION, role: "admin", permissions: { write: true, instance_admin: true },
  instance: { ...TEST_SESSION.instance!, chart: "sci", integrations: { enabled: [], proposed: ["qonto"] } } };

describe("page Intégrations", () => {
  it("activées, puis recommandées, puis les autres", () => {
    expect(sortIntegrations([item("smtp"), item("qonto", { recommended: true }), item("odoo", { enabled: true })]).map((v) => v.slug))
      .toEqual(["odoo", "qonto", "smtp"]);
  });

  it("badge « Recommandée » et invitation à activer", async () => {
    renderWithProviders(<IntegrationsPage />, { session: ADMIN });
    expect(await screen.findByText("Recommandée")).toBeTruthy();
    expect(screen.getByText("Activer et configurer →")).toBeTruthy();
    const cards = screen.getAllByRole("link").map((a) => a.getAttribute("href"));
    expect(cards).toEqual(["/configuration/integrations/odoo", "/configuration/integrations/qonto", "/configuration/integrations/smtp"]);
  });
});

describe("encart du tableau de bord", () => {
  it("propose Qonto et « Ne plus proposer » l'écarte", async () => {
    const user = userEvent.setup();
    renderWithProviders(<IntegrationProposals />, { session: ADMIN });
    expect(screen.getByText("Activez Qonto")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Configurer" }).getAttribute("href")).toBe("/configuration/integrations/qonto");
    await user.click(screen.getByRole("button", { name: "Ne plus proposer" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url === "/api/v1/integrations/qonto/dismiss")).toBe(true));
  });

  it("rien sans proposition", () => {
    renderWithProviders(<IntegrationProposals />);
    expect(screen.queryByText(/^Activez/)).toBeNull();
  });
});

describe("création d'une instance", () => {
  it("cases selon le plan comptable, recommandées cochées", async () => {
    const user = userEvent.setup();
    renderWithProviders(<InstancesPage />, { route: "/instances/new" });
    const helloasso = await screen.findByRole("checkbox", { name: "HelloAsso (recommandée)" });
    expect((helloasso as HTMLInputElement).checked).toBe(true);
    await user.click(screen.getByRole("combobox", { name: "Plan comptable" }));
    await user.click(await screen.findByRole("option", { name: "SCI" }));
    expect((screen.getByRole("checkbox", { name: "Qonto (recommandée)" }) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("checkbox", { name: "SMTP (emails)" }) as HTMLInputElement).checked).toBe(false);
    await user.type(screen.getByLabelText(/^Slug/), "sci-test");
    await user.type(screen.getByLabelText(/^Libellé/), "SCI Test");
    await user.click(screen.getByRole("button", { name: "Créer l'instance" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST" && c.url === "/api/v1/instances")?.body)
      .toMatchObject({ chart: "sci", integrations: ["qonto"] }));
  });
});
