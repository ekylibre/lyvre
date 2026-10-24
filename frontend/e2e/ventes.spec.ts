// Module Ventes (lot S7) : facture sans Qonto de bout en bout (saisie, émission, PDF, encaissement
// par la transaction bancaire), loyer mensuel jusqu'à la quittance, abonnement d'achat dont les
// échéances passées sont signalées manquantes.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

const year = new Date().getFullYear();
const iso = (d: Date) => d.toISOString().slice(0, 10);

test("facture : saisie, émission, PDF, encaissement", async ({ page }) => {
  await login(page, "SCI Ventes E2E", "/sales/new");
  await page.getByRole("combobox", { name: "Client" }).click();
  await page.getByRole("option", { name: "Client Ventes E2E" }).click();
  await page.getByLabel("Désignation (ligne 1)").fill("Conseil en gestion");
  await page.getByLabel("Prix unitaire HT (ligne 1)").fill("1200");
  await page.getByRole("button", { name: "Enregistrer le brouillon" }).click();
  await expect(page.getByRole("heading", { name: "Facture brouillon" })).toBeVisible();

  await page.getByRole("button", { name: "Émettre" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Émettre" }).click();
  await expect(page.getByRole("heading", { name: `Facture F-${year}-0001` })).toBeVisible();
  await expect(page.getByRole("link", { name: "PDF" })).toHaveAttribute("href", /\/api\/v1\/sales\/\d+\/pdf/);
  await expect(page.getByText("TVA non applicable", { exact: false })).toHaveCount(1);

  await page.getByRole("button", { name: "Encaisser" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("radio", { name: /VIR CLIENT VENTES E2E/ }).check();
  await dialog.getByRole("button", { name: "Encaisser" }).click();
  await expect(page.getByText("Payée", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("restant dû")).toBeVisible();

  // Lot F3 : facture et encaissement lettrés sans action, sur le compte du client.
  await page.goto("/lettering/");
  await page.getByText("Lettrées", { exact: true }).click();
  await expect(page.getByTitle("Lettré").first()).toBeVisible();
  await expect(page.getByRole("link", { name: new RegExp(`^VE-${year}-`) })).toBeVisible();
});

test("bail : avis d'échéance émis, encaissé, quittance", async ({ page }) => {
  await login(page, "SCI Ventes E2E", "/leases/");
  await page.getByRole("link", { name: "Nouveau bail" }).click();
  await page.getByRole("combobox", { name: "Locataire (preneur)" }).click();
  await page.getByRole("option", { name: "Client Ventes E2E" }).click();
  await page.getByRole("combobox", { name: "Type de bail" }).click();
  await page.getByRole("option", { name: "Bail d'habitation" }).click();
  await page.getByLabel(/^Désignation/).fill("Appartement 2B");
  const first = new Date();
  first.setDate(1);  // échéance le 1er : la première est celle du mois en cours
  await page.getByLabel(/^Date d'effet/).fill(iso(first));
  await page.getByRole("button", { name: "Suivant" }).click();
  // Étape 2 : un bien au forfait (cas simple, sans carte).
  await page.getByRole("button", { name: "Ajouter un bien" }).click();
  const item = page.getByRole("dialog");
  await item.getByLabel(/^Désignation/).fill("Appartement");
  await item.getByText("Forfait").click();
  await item.getByRole("button", { name: "Ajouter" }).click();
  await expect(page.getByRole("cell", { name: "Appartement", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Suivant" }).click();
  // Étape 3 : 9 600 € par an, soit 800 € par mois, plus 50 € de charges.
  await page.getByLabel("Prix Appartement").fill("9600");
  await page.getByLabel(/^Provisions sur charges/).fill("50");
  await page.getByRole("button", { name: "Valider le bail" }).click();
  await expect(page.getByRole("heading", { name: "Appartement 2B", exact: true })).toBeVisible();
  await expect(page.getByText(/^Rédigé le /)).toBeVisible();  // texte du bail figé à la validation (lot L2)
  await expect(page.getByRole("link", { name: "Aperçu (PDF)" })).toHaveAttribute("href", /\/preview\.pdf$/);

  await page.goto("/sales/due");
  await expect(page.getByText("1 échéance(s) préparée(s) à l'instant.")).toBeVisible();
  await page.getByRole("checkbox").nth(1).check();
  await page.getByRole("button", { name: "Émettre (1)" }).click();
  await expect(page.getByText("Aucune échéance à émettre.")).toBeVisible();

  await page.goto("/leases/");
  await page.getByRole("link", { name: "Appartement 2B" }).click();
  await page.getByRole("link", { name: new RegExp(`F-${year}-`) }).click();
  await page.getByRole("button", { name: "Encaisser" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByText("Chèque, espèces…").click();
  await dialog.getByRole("textbox", { name: "Encaissé sur" }).or(dialog.getByRole("combobox", { name: "Encaissé sur" })).click();
  await page.getByRole("option", { name: "Banque Ventes" }).click();
  await dialog.getByRole("button", { name: "Encaisser" }).click();
  await expect(page.getByRole("button", { name: "Quittance" })).toBeVisible();
  const popup = page.waitForEvent("popup");
  await page.getByRole("button", { name: "Quittance" }).click();
  await (await popup).close();

  await page.goto("/leases/");
  await page.getByRole("link", { name: "Appartement 2B" }).click();
  await expect(page.getByText(/^Quittance /)).toBeVisible();
});

test("abonnement : échéances passées sans facture signalées", async ({ page }) => {
  await login(page, "SCI Ventes E2E", "/subscriptions/");
  await page.getByRole("button", { name: "Nouvel abonnement" }).click();
  const form = page.getByRole("dialog");
  await form.getByLabel(/^Désignation/).fill("Box internet");
  await form.getByRole("combobox", { name: "Fournisseur" }).click();
  await page.getByRole("option", { name: "Orange E2E" }).click();
  await form.getByLabel(/^Montant TTC/).fill("45");
  const start = new Date();
  start.setMonth(start.getMonth() - 3, 1);
  await form.getByLabel(/^Début/).fill(iso(start));
  await form.getByRole("button", { name: "Créer l'abonnement" }).click();
  await expect(page.getByRole("heading", { name: "Box internet" })).toBeVisible();
  await expect(page.getByText("Manquante").first()).toBeVisible();
});

test("produit constaté d'avance proposé à la clôture (lot F4)", async ({ page }) => {
  await login(page, "SCI Ventes E2E", "/sales/");
  const csrf = (await (await page.request.get("/api/v1/session")).json()).csrf_token;
  const call = async (method: string, url: string, data?: unknown) => {
    const resp = await page.request.fetch(url, { method, data, headers: { "X-CSRFToken": csrf } });
    expect(resp.ok(), await resp.text()).toBeTruthy();
    return resp.json();
  };
  const client = (await call("GET", "/api/v1/sales/form-options")).clients.find((c: { label: string }) => c.label === "Client Ventes E2E").value;
  const sale = (await call("POST", "/api/v1/sales", { entity_id: client, issue_date: iso(new Date()),
    service_start: `${year}-12-01`, service_end: `${year + 1}-11-30`,
    lines: [{ label: "Maintenance annuelle", quantity: "1", unit_price: "3650", vat_rate: "0", account_code: "706" }] })).item;
  await call("POST", `/api/v1/sales/${sale.id}/issue`);
  const fy = (await call("GET", "/api/v1/fiscal-years")).items.find((f: { label: string }) => f.label === String(year));

  await page.goto(`/fiscal-years/${fy.id}/closing`);
  await page.getByRole("button", { name: /2\. Écritures d'inventaire/ }).click();
  await expect(page.getByText("Propositions de charges et produits constatés d'avance")).toBeVisible();
  await page.getByLabel(/^Retenir F-/).check();
  await page.getByRole("button", { name: "Passer les écritures (1)" }).click();
  await expect(page.getByText("passée", { exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: /Produit constaté d'avance/ }).first()).toBeVisible();
});

test("modèles de bail : livrés, à relire (lot L2)", async ({ page }) => {
  await login(page, "SCI Ventes E2E", "/lease-templates/");
  await expect(page.getByRole("tab", { name: /Bail dérogatoire commercial/ })).toBeVisible();
  await expect(page.getByText("Modèle livré, à relire")).toBeVisible();
  await page.getByRole("tab", { name: /Bail d'habitation/ }).click();
  await expect(page.getByText("CONTRAT DE LOCATION")).toBeVisible();
});
