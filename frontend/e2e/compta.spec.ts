// Parcours compta (phase D) : saisie d'une écriture au clavier (« = », Ctrl+Maj+Entrée),
// fiche, balance, suppression confirmée.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("saisie d'une écriture au clavier, balance, suppression", async ({ page }) => {
  await login(page, "SCI E2E", "/entries/new");
  await expect(page.getByRole("heading", { name: "Saisir une écriture" })).toBeVisible();

  await page.getByLabel("Description").fill("Achat perceuse");
  await page.keyboard.press("Enter");  // vers le compte de la 1re ligne
  await expect(page.getByLabel("Compte, ligne 1")).toBeFocused();
  await page.keyboard.type("6063");
  await page.getByRole("option", { name: /606300/ }).click();
  await page.getByLabel("Débit, ligne 1").fill("89,90");
  await page.getByLabel("Compte, ligne 2").click();
  await page.keyboard.type("512");
  await page.getByRole("option", { name: /512000/ }).click();
  await page.getByLabel("Crédit, ligne 2").click();
  await page.keyboard.press("=");
  await expect(page.getByLabel("Crédit, ligne 2")).toHaveValue("89,90");
  await expect(page.getByText("Équilibrée : 89,90 €")).toBeVisible();

  await page.keyboard.press("Control+Shift+Enter");
  await expect(page).toHaveURL(/\/entries\/\d+$/);
  const heading = page.getByRole("heading", { name: /AC-\d{4}-\d{4}/ });
  await expect(heading).toBeVisible();
  const reference = ((await heading.textContent()) ?? "").match(/AC-\d{4}-\d{4}/)![0];
  await expect(page.getByRole("cell", { name: /606300/ })).toBeVisible();

  await page.goto("/reports/balance");
  await expect(page.getByRole("cell", { name: "606300" })).toBeVisible();
  await expect(page.getByText(/Total débit/)).toBeVisible();

  await page.goBack();
  await page.getByRole("button", { name: "Supprimer" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Supprimer" }).click();
  await expect(page).toHaveURL(/\/entries\/$/);
  await expect(page.getByText(`Écriture ${reference} supprimée.`)).toBeVisible();
  await expect(page.getByText("Écriture introuvable.")).toHaveCount(0);
  await expect(page.getByRole("link", { name: reference })).toHaveCount(0);
});

test("tableau de bord de l'exercice", async ({ page }) => {
  await login(page, "SCI E2E", "/");
  await expect(page.getByRole("heading", { name: "Tableau de bord" })).toBeVisible();
  await expect(page.getByText("Résultat courant")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Résultat mensuel" })).toBeVisible();
});

test("validation puis contrepassation d'une écriture (lot F1)", async ({ page }) => {
  await login(page, "SCI E2E", "/entries/new");
  await page.getByLabel("Description").fill("Achat scie");
  await page.getByLabel("Compte, ligne 1").click();
  await page.keyboard.type("6063");
  await page.getByRole("option", { name: /606300/ }).click();
  await page.getByLabel("Débit, ligne 1").fill("45,00");
  await page.getByLabel("Compte, ligne 2").click();
  await page.keyboard.type("512");
  await page.getByRole("option", { name: /512000/ }).click();
  await page.getByLabel("Crédit, ligne 2").click();
  await page.keyboard.press("=");
  await page.keyboard.press("Control+Shift+Enter");
  await expect(page).toHaveURL(/\/entries\/\d+$/);
  await expect(page.getByText("Brouillard", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Valider" }).click();
  await expect(page.getByText(/^Validée n° \d+$/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Modifier" })).toHaveCount(0);
  await expect(page.getByText(/elle ne se modifie plus/)).toBeVisible();
  await expect(page.getByText("Validation", { exact: true })).toBeVisible();  // historique

  await page.getByRole("button", { name: "Contrepasser" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel(/Motif/).fill("Doublon");
  await dialog.getByRole("button", { name: "Contrepasser" }).click();
  await expect(page.getByText(/Contrepassation de l'écriture/)).toBeVisible();
  await expect(page.getByText("Brouillard", { exact: true })).toBeVisible();
});
