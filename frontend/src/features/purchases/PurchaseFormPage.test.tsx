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
});
