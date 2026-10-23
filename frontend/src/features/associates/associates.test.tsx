import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { Route, Routes } from "react-router";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import AssociateDetailPage from "./AssociateDetailPage";
import AssociatesPage from "./AssociatesPage";
import { balanceLabel } from "./types";

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));
const ADMIN = { ...TEST_SESSION, role: "admin" as const, permissions: { write: true, instance_admin: true } };
const PARENT = { id: 3, name: "Parent", entity_id: 8, account_code: "4551001", account_label: "Compte courant — Parent",
  parts: { full: 0, usufruct: 300, bare: 0 }, percent: { full: 0, usufruct: 30, bare: 0 }, balance_cents: 8696308,
  interest_rate: "", notes: null, is_out: false };
const META = { at: "2026-10-23", total_parts: 1000, balances_total_cents: 8696308, next_account_code: "4551002",
  entities: [{ value: "9", label: "Agnès Martin" }] };

beforeEach(() => {
  calls = [];
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    const body = init.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, url, body });
    if (url.startsWith("/api/v1/associates/3")) {
      return json(200, { item: { ...PARENT, balance_cents: -1500 }, meta: { can_delete: false, account_locked: true } });
    }
    if (url.startsWith("/api/v1/associates") && method === "GET") return json(200, { items: [PARENT], meta: META });
    if (url === "/api/v1/associates" && method === "POST") {
      return json(201, { item: { ...PARENT, id: 4 }, notices: [{ level: "success", message: "Ajouté." }] });
    }
    return json(404, { error: { code: "not_found", message: "?" } });
  }) as typeof fetch);
});

afterEach(() => vi.restoreAllMocks());

describe("associés", () => {
  it("liste les parts par nature et le sens du solde", async () => {
    renderWithProviders(<AssociatesPage />, { route: "/associates/" });
    expect(await screen.findByText("Parent")).toBeTruthy();
    expect(screen.getByText("300")).toBeTruthy();
    expect(screen.getByText("30 %")).toBeTruthy();
    expect(screen.getAllByText("dû à l'associé").length).toBeGreaterThan(0);
    // Trésorier : pas de création.
    expect(screen.queryByRole("button", { name: "Nouvel associé" })).toBeNull();
    expect(balanceLabel(-1)).toBe("dû par l'associé");
    expect(balanceLabel(0)).toBe("soldé");
  });

  it("l'administrateur ajoute un associé depuis un tiers existant", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AssociatesPage />, { route: "/associates/new", session: ADMIN });
    await user.click(await screen.findByRole("combobox", { name: "Tiers" }));
    await user.click(await screen.findByRole("option", { name: "Agnès Martin" }));
    expect((screen.getByLabelText("Compte courant") as HTMLInputElement).placeholder).toBe("4551002");
    await user.click(screen.getByRole("button", { name: "Ajouter l'associé" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toEqual(
      { entity_id: "9", account_code: "", interest_rate: "", notes: "" }));
  });

  it("fiche : compte verrouillé et solde débiteur signalé", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <Routes><Route path="/associates/:associate_id" element={<AssociateDetailPage />} /></Routes>,
      { route: "/associates/3", session: ADMIN });
    expect(await screen.findByText("dû par l'associé")).toBeTruthy();
    expect(screen.getByText("Usufruit")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Retirer" })).toBeNull(); // historique : pas de suppression
    await user.click(screen.getByRole("button", { name: "Modifier" }));
    expect((await screen.findByLabelText("Compte courant") as HTMLInputElement).disabled).toBe(true);
  });
});
