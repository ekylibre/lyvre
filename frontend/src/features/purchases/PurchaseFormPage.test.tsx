import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { renderWithProviders } from "../../test/render";
import PurchaseFormPage from "./PurchaseFormPage";

type Call = { method: string; url: string; body: any }; // eslint-disable-line @typescript-eslint/no-explicit-any
let calls: Call[];

const json = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status }));

beforeEach(() => {
  calls = [];
  vi.spyOn(notifications, "show").mockReturnValue("id");
  vi.spyOn(globalThis, "fetch").mockImplementation(((input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const method = init.method ?? "GET";
    const body = init.body ? JSON.parse(init.body as string) : undefined;
    calls.push({ method, url, body });
    if (url === "/api/v1/purchases/form-options") {
      return json(200, { entities: [{ value: "4", label: "EDF" }], products: [], qonto: { available: false, message: null, upload: false },
        charge_accounts: [{ value: "6061", label: "6061 — Fournitures non stockables" }] });
    }
    if (url === "/api/v1/purchases" && method === "POST") {
      if (!body.total) return json(422, { error: { code: "validation_error", message: "x", fields: { form: ["Le montant TTC est obligatoire."] } } });
      if (!body.confirm_duplicate) {
        return json(409, { error: { code: "duplicate", message: "Doublon possible.",
          duplicates: [{ id: 7, label: "Facture F-1", issue_date: "2026-09-02", total_cents: 1200 }] } });
      }
      return json(201, { item: { id: 9, url: "/purchases/9" }, notices: [{ level: "success", message: "Facture enregistrée." }] });
    }
    if (url === "/api/v1/bank-transactions/7/purchase-draft") {
      return json(200, { token: "a".repeat(32), preview: { url: "/purchases/staged/x", mime: "application/pdf" },
        transaction: { id: 7, date: "2026-07-02", label: "Google Workspace_ekyli", amount_cents: -5832, bank_account: "Qonto" },
        form: { values: { total: "58,32", issue_date: "2026-07-02", invoice_number: "5214789632", entity_id: "4" }, checks: ["total"],
          rows: [{ product_id: "", account_code: "6061", label: "Google", untaxed: "48,60", vat_rate: "20", vat: "9,72", total: "58,32" }],
          warnings: [], source: "text" } });
    }
    if (url === "/api/v1/chart-of-accounts" && method === "POST") {
      return json(201, { item: { id: 30, code: body.code, label: body.label }, notices: [] });
    }
    if (url === "/api/v1/products" && method === "POST") {
      return json(201, { item: { id: 12, name: body.name, purchase_account: { code: body.purchase_account_code }, vat_rate: body.vat_rate },
        notices: [{ level: "success", message: "Produit créé." }] });
    }
    return json(404, { error: { code: "not_found", message: "?" } });
  }) as typeof fetch);
});

afterEach(() => vi.restoreAllMocks());

describe("saisie d'une facture d'achat", () => {
  it("propose le dépôt de la pièce ou la saisie sans fichier", async () => {
    renderWithProviders(<PurchaseFormPage />, { route: "/purchases/new" });
    expect(await screen.findByText("Déposer la facture ici ou cliquer pour la choisir")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Saisir sans fichier" }).getAttribute("href")).toBe("/purchases/new?manual=1");
  });

  it("« Saisir sans fichier » ouvre le formulaire vide sans recharger la page", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PurchaseFormPage />, { route: "/purchases/new" });
    await user.click(await screen.findByRole("link", { name: "Saisir sans fichier" }));
    expect(await screen.findByRole("combobox", { name: "Fournisseur" })).toBeTruthy();
    expect(screen.queryByText("Déposer la facture ici ou cliquer pour la choisir")).toBeNull();
  });

  it("affiche les erreurs, puis le doublon à confirmer", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PurchaseFormPage />, { route: "/purchases/new?manual=1" });
    await user.type(await screen.findByLabelText("N° de facture"), "F-1");
    await user.type(screen.getByLabelText(/^Date/), "2026-09-02");
    await user.type(screen.getByLabelText("HT (ligne 1)"), "10");
    await user.type(screen.getByLabelText("Taux de TVA (ligne 1)"), "20");
    expect(screen.getAllByText("12,00 €")).toHaveLength(2); // TTC de la ligne et total des lignes

    // TTC manquant : le champ est requis côté navigateur, on contourne pour tester l'API.
    screen.getByLabelText(/^TTC/).removeAttribute("required");
    await user.click(screen.getByRole("button", { name: "Enregistrer la facture" }));
    expect(await screen.findByText("Le montant TTC est obligatoire.")).toBeTruthy();

    await user.type(screen.getByLabelText(/^TTC/), "12,00");
    await user.click(screen.getByRole("button", { name: "Enregistrer la facture" }));
    expect(await screen.findByText("Doublon possible")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Facture F-1" }).getAttribute("href")).toBe("/purchases/7");

    await user.click(screen.getByLabelText("Ce n'est pas un doublon : enregistrer quand même"));
    await user.click(screen.getByRole("button", { name: "Enregistrer la facture" }));
    await waitFor(() => expect(calls.filter((c) => c.method === "POST")).toHaveLength(3));
    const last = calls.filter((c) => c.method === "POST").at(-1)!.body;
    expect(last).toMatchObject({ invoice_number: "F-1", issue_date: "2026-09-02", total: "12,00", confirm_duplicate: true,
      send_to_qonto: false, rows: [{ untaxed: "10", vat_rate: "20", vat: "" }] });
  });

  it("crée un produit depuis la ligne avec le compte et le taux saisis", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PurchaseFormPage />, { route: "/purchases/new?manual=1" });
    await user.type(await screen.findByLabelText("Compte (ligne 1)", { selector: "input" }), "6061");
    await user.type(screen.getByLabelText("Taux de TVA (ligne 1)"), "20");
    await user.type(screen.getByLabelText("Produit (ligne 1)", { selector: "input" }), "Electricité");
    await user.click(await screen.findByRole("option", { name: "+ Créer « Electricité »" }));
    expect((await screen.findByLabelText(/^Libellé/, { selector: "[role=dialog] input" }) as HTMLInputElement).value).toBe("Electricité");
    await user.click(screen.getByRole("button", { name: "Créer le produit" }));
    await waitFor(() => expect(calls.find((c) => c.url === "/api/v1/products")?.body).toEqual(
      { name: "Electricité", kind: "purchase", purchase_account_code: "6061", vat_rate: "20" }));
    await waitFor(() => expect((screen.getByLabelText("Produit (ligne 1)", { selector: "input" }) as HTMLInputElement).value).toBe("Electricité"));
    expect((screen.getByLabelText("Libellé (ligne 1)") as HTMLInputElement).value).toBe("Electricité");
    // La fenêtre du produit n'envoie pas le formulaire de la facture (événement remonté par le portail React).
    expect(calls.filter((c) => c.url === "/api/v1/purchases")).toEqual([]);
  });

  it("crée le compte de charge absent du plan avec le produit", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PurchaseFormPage />, { route: "/purchases/new?manual=1" });
    await user.type(await screen.findByLabelText("Compte (ligne 1)", { selector: "input" }), "6063");
    await user.type(screen.getByLabelText("Produit (ligne 1)", { selector: "input" }), "Petit outillage");
    await user.click(await screen.findByRole("option", { name: "+ Créer « Petit outillage »" }));
    await user.type(await screen.findByLabelText(/^Libellé du compte 6063/), "Fournitures d'entretien et de petit équipement");
    await user.click(screen.getByRole("button", { name: "Créer le produit" }));
    await waitFor(() => expect(calls.find((c) => c.url === "/api/v1/products")?.body).toMatchObject(
      { name: "Petit outillage", purchase_account_code: "6063" }));
    expect(calls.find((c) => c.url === "/api/v1/chart-of-accounts")?.body).toEqual(
      { code: "6063", label: "Fournitures d'entretien et de petit équipement", account_type: "EXPENSE" });
    expect(calls.filter((c) => c.url === "/api/v1/purchases")).toEqual([]);
  });

  it("depuis le justificatif d'une transaction Qonto : prérempli, relié à la transaction, sans envoi à Qonto", async () => {
    const user = userEvent.setup();
    renderWithProviders(<PurchaseFormPage />, { route: "/purchases/new?bank_transaction_id=7" });
    expect(await screen.findByText(/Facture du paiement Qonto du 02\/07\/2026/)).toBeTruthy();
    expect(screen.queryByRole("checkbox", { name: /Envoyer à Qonto/ })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Enregistrer la facture" }));
    await waitFor(() => expect(calls.find((c) => c.url === "/api/v1/purchases" && c.method === "POST")?.body)
      .toMatchObject({ bank_transaction_id: 7, token: "a".repeat(32), send_to_qonto: false }));
  });
});
