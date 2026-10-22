// Reçus fiscaux, paramètres (lot B.1) : mentions requises listées ; activation refusée tant
// qu'elles manquent ; adresse et nature d'un donateur dans la fiche du tiers.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("reçus fiscaux : mentions manquantes, activation refusée ; adresse d'un donateur", async ({ page }) => {
  await login(page, "Association E2E", "/configuration/receipts");
  await expect(page.getByRole("heading", { name: "Reçus fiscaux" })).toBeVisible();
  await expect(page.getByText("Image de la signature")).toBeVisible();
  await page.getByLabel("Organisme d'intérêt général", { exact: false }).check();
  await page.getByLabel(/Je déclare, au nom de la structure/).check();
  await page.getByLabel("Reçus fiscaux activés").check();
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByText(/Activation impossible, à compléter/).first()).toBeVisible();

  await page.goto("/entities/new");
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Nom").fill("Donatrice E2E");
  await dialog.getByText("Particulier").click();
  await dialog.getByLabel("Adresse", { exact: true }).fill("3 rue des Dons");
  await dialog.getByLabel("Code postal").fill("75001");
  await dialog.getByLabel("Ville").fill("Paris");
  await dialog.getByRole("button", { name: "Créer le tiers" }).click();
  await expect(page.getByText("Entité « Donatrice E2E » créée.")).toBeVisible();
});
