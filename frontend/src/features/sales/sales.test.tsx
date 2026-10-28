// Ventes (lot S1) : totaux estimés, saisie d'un brouillon depuis le catalogue, fiche (émission,
// avoir, envoi sans SMTP).
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { Route, Routes } from "react-router";
import { renderWithProviders, TEST_SESSION } from "../../test/render";
import type { Session } from "../../api/session";
import SaleDetailPage from "./SaleDetailPage";
import SaleFormPage from "./SaleFormPage";
import { estimate, EMPTY_SALE_LINE, type SaleDetail } from "./types";

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];
const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

const OPTIONS = {
  clients: [{ value: "4", label: "Client SARL", vat_regime: "fr", vat_number: "" },
    { value: "5", label: "Agri GmbH", vat_regime: "eu", vat_number: "DE812871812" }],
  vat_regimes: [{ value: "fr", label: "France" }, { value: "eu", label: "Union européenne" }, { value: "world", label: "Hors Union européenne" }],
  products: [{ value: "9", label: "Audit", account: "706", rate: "20", price: "500,00", unit: "jour", description: "Audit annuel", nature: "services" }],
  sale_accounts: [{ value: "706", label: "706 — Prestations" }], default_account: "706", projects: [], units: ["heure", "jour"],
  operation_types: [{ value: "services", label: "Prestation de services" }], vat_mode: "receipts", vat_liable: true, payment_terms_days: 30,
  qonto: true,
};

function detail(fields: Partial<SaleDetail> = {}): SaleDetail {
  return {
    id: 7, kind: "invoice", kind_label: "Facture", status: "issued", status_label: "Émise", number: "F-2026-0001", source: "app",
    client: { id: 4, name: "Client SARL", address_line1: "2 avenue X", address_line2: null, postal_code: "69001", city: "Lyon",
      country: "France", siren: "987654321", vat_number: null, email: "compta@client.example" },
    issue_date: "2026-10-23", due_date: "2026-11-22", untaxed_cents: 50000, tax_cents: 10000, total_cents: 60000, paid_cents: 0,
    sent_at: null, overdue: false, service_start: null, service_end: null, operation_type: "services", purchase_order: "",
    terms: "", header: "", footer: "", vat_mode: "receipts", credit_reason: null, vat_regime: "fr", vat_exemptions: [],
    lines: [{ id: 1, ...EMPTY_SALE_LINE, label: "Audit", unit_price: "500,00", vat_rate: "20", account_code: "706",
      untaxed_cents: 50000, vat_cents: 10000, total_cents: 60000 }],
    vat_rows: [{ rate: 2000, base: 50000, tax: 10000 }], journal_entry: { id: 3, reference: "VE-0001" }, invoice: null,
    credit_notes: [], remaining_credit_cents: 60000, issue_problems: [], recipients: ["compta@client.example"], emails: [],
    pdf_url: "/api/v1/sales/7/pdf", due_cents: 60000, reminder_count: 0, last_reminder_at: null, payments: [],
    validity_date: null, quote: null, invoices: [], qonto_emit: false, qonto_status: null, qonto_error: null,
    lease: null, recurrence_id: null, rent_receipts: [], ...fields,
  };
}

let current: SaleDetail;
beforeEach(() => {
  calls = [];
  current = detail();
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    calls.push({ method, url, body: init.body ? JSON.parse(init.body as string) : undefined });
    if (url === "/api/v1/sales/form-options") return json(200, OPTIONS);
    if (url === "/api/v1/sales" && method === "POST") return json(201, { item: detail({ id: 8, status: "draft", number: null }), notices: [] });
    if (url === "/api/v1/sales/7" && method === "GET") return json(200, { item: current });
    if (url === "/api/v1/sales/7/payment-options") return json(200, { due_cents: 60000,
      candidates: [{ id: 31, date: "2026-10-25", label: "VIR CLIENT SARL", amount_cents: 60000, account: "Compte courant", same_client: true, exact: true, rule: false }],
      accounts: [{ value: "1", label: "Compte courant", kind: "bank" }], methods: [{ value: "check", label: "Chèque" }] });
    if (url === "/api/v1/sales/match") return json(200, { items: [detail({ status: "paid", due_cents: 0 })], notices: [] });
    if (url === "/api/v1/sales/7/to-invoice") return json(201, { item: detail({ id: 12, status: "draft", number: null }), notices: [] });
    if (url === "/api/v1/sales/7/quote-status") return json(200, { item: detail({ kind: "quote", status: "accepted", number: "D-2026-0001" }), notices: [] });
    if (url === "/api/v1/sales/7/credit-note") return json(201, { item: detail({ id: 9, kind: "credit_note", status: "draft", number: null }), notices: [] });
    return json(404, { error: { code: "not_found", message: "?" } });
  }) as typeof fetch);
});
afterEach(() => vi.restoreAllMocks());

describe("totaux estimés", () => {
  it("TVA arrondie par taux, comme le serveur", () => {
    const rows = [{ ...EMPTY_SALE_LINE, label: "A", quantity: "2,5", unit_price: "80", vat_rate: "20" },
      { ...EMPTY_SALE_LINE, label: "B", quantity: "3", unit_price: "10,01", discount: "10", vat_rate: "5,5" }];
    expect(estimate(rows, false)).toEqual({ untaxed: 22703, tax: 4149, total: 26852 });
    expect(estimate(rows, true)).toEqual({ untaxed: 22703, tax: 0, total: 22703 });
  });
});

describe("saisie d'une facture", () => {
  it("le produit remplit la ligne, puis brouillon enregistré", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Routes><Route path="/sales/new" element={<SaleFormPage />} /></Routes>, { route: "/sales/new" });
    await user.click(await screen.findByRole("combobox", { name: "Client" }));
    await user.click(await screen.findByRole("option", { name: "Client SARL" }));
    await user.click(screen.getByRole("combobox", { name: "Produit (ligne 1)" }));
    await user.click(await screen.findByRole("option", { name: "Audit" }));
    expect((screen.getByLabelText("Désignation (ligne 1)") as HTMLInputElement).value).toBe("Audit");
    expect((screen.getByLabelText("Prix unitaire HT (ligne 1)") as HTMLInputElement).value).toBe("500,00");
    expect(within(screen.getByLabelText("Totaux estimés")).getByText(/600,00/)).toBeTruthy();
    const qonto = screen.getByRole("checkbox", { name: /Émettre avec Qonto/ }) as HTMLInputElement;
    expect(qonto.checked).toBe(false);  // décochée par défaut
    await user.click(qonto);
    await user.click(screen.getByRole("button", { name: "Enregistrer le brouillon" }));
    await waitFor(() => expect(calls.find((c) => c.method === "POST")?.body).toMatchObject({
      entity_id: "4", qonto_emit: true, lines: [{ product_id: "9", label: "Audit", unit_price: "500,00", vat_rate: "20", account_code: "706", unit: "jour" }] }));
  });

  it("client de l'UE avec n° de TVA : pas de TVA française (lot T2)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Routes><Route path="/sales/new" element={<SaleFormPage />} /></Routes>, { route: "/sales/new" });
    await user.click(await screen.findByRole("combobox", { name: "Client" }));
    await user.click(await screen.findByRole("option", { name: "Agri GmbH" }));
    expect((screen.getByRole("combobox", { name: "Régime TVA du client" }) as HTMLInputElement).value).toBe("Union européenne");
    expect(screen.getByText(/Pas de TVA française/)).toBeTruthy();
  });
});

describe("fiche d'une facture", () => {
  const ADMIN: Session = { ...TEST_SESSION, role: "admin", permissions: { write: true, instance_admin: true } };
  const page = (session = ADMIN) => renderWithProviders(<Routes><Route path="/sales/:sale_id" element={<SaleDetailPage />} /></Routes>,
    { route: "/sales/7", session });

  it("brouillon incomplet : émission impossible, motifs affichés", async () => {
    current = detail({ status: "draft", number: null, issue_problems: ["Mention manquante : SIREN (Configuration › Structure)."] });
    page();
    expect(await screen.findByText("Mention manquante : SIREN (Configuration › Structure).")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Émettre" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("avoir : motif et lignes", async () => {
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole("button", { name: "Avoir" }));
    await user.type(screen.getByLabelText(/Motif/), "Erreur de facturation");
    await user.click(screen.getByRole("button", { name: "Créer le brouillon d'avoir" }));
    await waitFor(() => expect(calls.find((c) => c.url.endsWith("/credit-note"))?.body).toEqual({ reason: "Erreur de facturation", line_ids: [1] }));
  });

  it("envoi sans SMTP : l'intégration est nécessaire", async () => {
    const user = userEvent.setup();
    page({ ...ADMIN, instance: { ...ADMIN.instance!, integrations: { enabled: [], proposed: [] } } });
    await user.click(await screen.findByRole("button", { name: "Envoyer" }));
    expect(await screen.findByText("L'envoi par email nécessite l'intégration SMTP (emails), désactivée.")).toBeTruthy();
  });

  it("encaisser par la transaction proposée", async () => {
    const user = userEvent.setup();
    page();
    await user.click(await screen.findByRole("button", { name: "Encaisser" }));
    await user.click(await screen.findByRole("radio", { name: /VIR CLIENT SARL/ }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Encaisser" }));
    await waitFor(() => expect(calls.find((c) => c.url === "/api/v1/sales/match")?.body).toEqual({
      bank_transaction_id: 31, allocations: [{ sale_id: 7, amount_cents: 60000 }] }));
  });

  it("relancer une facture échue", async () => {
    current = detail({ overdue: true });
    page();
    expect(await screen.findByRole("button", { name: "Relancer" })).toBeTruthy();
  });

  it("devis émis : accepter, puis transformer en facture", async () => {
    const user = userEvent.setup();
    current = detail({ kind: "quote", number: "D-2026-0001", status: "issued", status_label: "Envoyé", due_date: null,
      validity_date: "2026-11-22", journal_entry: null });
    page();
    expect(await screen.findByText("Devis D-2026-0001")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Encaisser" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Accepté" }));
    await waitFor(() => expect(calls.find((c) => c.url.endsWith("/quote-status"))?.body).toEqual({ status: "accepted" }));
    await user.click(screen.getByRole("button", { name: "Transformer en facture" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url.endsWith("/to-invoice"))).toBe(true));
  });
});
