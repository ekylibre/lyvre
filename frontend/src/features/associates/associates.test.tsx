import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { Route, Routes } from "react-router";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import AssociateDetailPage from "./AssociateDetailPage";
import { AssociatePaymentForm } from "./AssociatePaymentForm";
import AssociatesPage from "./AssociatesPage";
import { chartRows } from "./BalancesChart";
import ExpensesPage from "./ExpensesPage";
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
    if (url === "/api/v1/associates/3/statement") {
      return json(200, { opening_cents: 0, closing_cents: -1500, lines: [{ date: "2026-05-02", entry_id: 9, reference: "AS-1",
        label: "Remboursement", origin: "Banque", amount_cents: -1500, balance_cents: -1500 }] });
    }
    if (url === "/api/v1/associate-expenses" && method === "POST") return json(201, { item: {}, notices: [] });
    if (url.startsWith("/api/v1/associate-expenses")) {
      return json(200, { items: [], meta: { associates: [{ value: "3", label: "Parent" }],
        charge_accounts: [{ value: "6068", label: "6068 — Autres achats" }] } });
    }
    if (url === "/api/v1/purchases/7/associate-payment") return json(200, { notices: [] });
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
      { entity_id: "9", account_code: "", interest_rate: "", notes: "", is_manager: false }));
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

  it("fiche : relevé du compte courant", async () => {
    renderWithProviders(
      <Routes><Route path="/associates/:associate_id" element={<AssociateDetailPage />} /></Routes>,
      { route: "/associates/3" });
    expect(await screen.findByText("AS-1")).toBeTruthy();
    expect(screen.getByText("Banque")).toBeTruthy();
  });

  it("graphique : une ligne par exercice, en euros", () => {
    expect(chartRows({ years: ["2025", "2026"], series: [{ name: "Lola", values: [0, 7059] }] }))
      .toEqual([{ exercice: "2025", Lola: 0 }, { exercice: "2026", Lola: 70.59 }]);
  });

  it("facture réglée par un associé", async () => {
    const user = userEvent.setup();
    const onDone = vi.fn();
    renderWithProviders(<AssociatePaymentForm purchaseId={7} totalCents={7059} associates={[{ value: "3", label: "Parent" }]}
      invalidate={[["purchases"]]} onDone={onDone} />);
    expect(screen.getByText(/70,59/)).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Enregistrer le règlement" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(calls.find((c) => c.url === "/api/v1/purchases/7/associate-payment")?.body)
      .toMatchObject({ associate_id: "3" });
  });

  it("note de frais saisie par le trésorier", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ExpensesPage />, { route: "/associate-expenses/new" });
    await user.type(await screen.findByLabelText(/^Libellé/), "Ampoules");
    // Un seul associé : il est présélectionné.
    expect((screen.getByRole("combobox", { name: "Associé" }) as HTMLInputElement).value).toBe("Parent");
    await user.click(screen.getByRole("combobox", { name: "Compte de charge" }));
    await user.click(await screen.findByRole("option", { name: "6068 — Autres achats" }));
    await user.type(screen.getByLabelText(/^HT/), "10");
    await user.type(screen.getByLabelText(/^Taux de TVA/), "20");
    await user.click(screen.getByRole("button", { name: "Enregistrer la note de frais" }));
    await waitFor(() => expect(calls.find((c) => c.url === "/api/v1/associate-expenses" && c.method === "POST")?.body)
      .toMatchObject({ associate_id: "3", label: "Ampoules", account_code: "6068", untaxed: "10", vat_rate: "20" }));
  });
});
