// Caisse (lot D.1) : création d'une caisse (compte 53), entrée d'espèces, dépôt en banque par le
// compte 581 ; solde courant de la caisse.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("caisse : création, entrée d'espèces, dépôt en banque", async ({ page }) => {
  await login(page, "SCI E2E", "/bank-accounts/new");
  const dialog = page.getByRole("dialog", { name: "Créer un compte bancaire ou une caisse" });
  await dialog.getByText("Caisse (espèces)").click();
  await dialog.getByLabel("Libellé").fill("Caisse E2E");
  await dialog.getByRole("button", { name: "Créer le compte" }).click();
  await page.getByRole("link", { name: "Caisse E2E" }).click();
  await expect(page.getByRole("heading", { name: "Caisse E2E" })).toBeVisible();

  await page.getByRole("button", { name: "Nouveau mouvement" }).click();
  const movement = page.getByRole("dialog", { name: "Nouveau mouvement de caisse" });
  await movement.getByLabel("Montant").fill("120");
  await movement.getByLabel("Libellé").fill("Loyer en espèces");
  await movement.getByRole("textbox", { name: "Compte de contrepartie" }).fill("706000");
  await page.getByRole("option", { name: /706000/ }).click();
  await movement.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/Mouvement de caisse enregistré/)).toBeVisible();

  await page.getByRole("button", { name: "Dépôt en banque" }).click();
  const deposit = page.getByRole("dialog", { name: "Dépôt d'espèces en banque" });
  await deposit.getByLabel("Montant").fill("100");
  await deposit.getByRole("button", { name: "Enregistrer le dépôt" }).click();
  await expect(page.getByText(/Dépôt en banque enregistré/)).toBeVisible();
  await expect(page.getByText("dépôt en banque", { exact: true })).toBeVisible();
  await expect(page.getByText("20,00 €").first()).toBeVisible();
});
