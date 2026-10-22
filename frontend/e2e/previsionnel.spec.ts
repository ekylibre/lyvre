// Prévisionnel de trésorerie (lot C.4) : saisie manuelle répétée, solde négatif signalé sur la
// page et au tableau de bord, puis retrait de la saisie.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("prévisionnel : saisie répétée, alerte de solde négatif, retrait", async ({ page }) => {
  await login(page, "SCI E2E", "/treasury/forecast");
  await expect(page.getByRole("heading", { name: "Prévisionnel de trésorerie" })).toBeVisible();
  await page.getByRole("button", { name: "Ajouter une saisie" }).click();
  const dialog = page.getByRole("dialog", { name: "Ajouter une saisie" });
  await dialog.getByLabel("Libellé").fill("Travaux toiture");
  const now = new Date();
  const day = `05/${String(now.getMonth() + 1).padStart(2, "0")}/${now.getFullYear()}`;
  await dialog.getByRole("textbox", { name: /^Date/ }).fill(day);
  await dialog.getByRole("textbox", { name: /^Date/ }).press("Tab");
  await dialog.getByLabel("Montant").fill("1000000");
  await dialog.getByRole("button", { name: "Ajouter" }).click();
  await expect(page.getByText("« Travaux toiture » ajouté au prévisionnel.")).toBeVisible();
  await expect(page.getByText("Trésorerie négative prévue")).toBeVisible();
  await expect(page.getByRole("row", { name: /Travaux toiture/ })).toBeVisible();

  await page.goto("/");
  await expect(page.getByText("Trésorerie négative prévue")).toBeVisible();

  await page.goto("/treasury/forecast");
  await page.getByRole("row", { name: /Travaux toiture/ }).getByRole("button", { name: "Retirer" }).click();
  await page.getByRole("dialog", { name: "Retirer « Travaux toiture » ?" }).getByRole("button", { name: "Retirer" }).click();
  await expect(page.getByText("Aucune saisie")).toBeVisible();
});
