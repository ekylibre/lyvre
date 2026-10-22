// Parcours « écran simple » (phase B) : créer, refuser un doublon, clôturer après
// confirmation ; colonnes masquées retrouvées après reconnexion (préférences du compte).
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("journaux : création, doublon refusé au champ", async ({ page }) => {
  await login(page, "Association E2E", "/journals/");
  await expect(page.getByRole("heading", { name: "Journaux" })).toBeVisible();

  await page.getByRole("button", { name: "Créer un journal" }).click();
  await expect(page).toHaveURL(/\/journals\/new$/);
  const dialog = page.getByRole("dialog", { name: "Créer un journal" });
  await dialog.getByLabel("Code").fill("od");
  await dialog.getByLabel("Libellé").fill("Opérations diverses");
  await dialog.getByRole("button", { name: "Créer le journal" }).click();
  await expect(page.getByText("Journal OD créé.")).toBeVisible();
  await expect(page).toHaveURL(/\/journals\/$/);
  await expect(page.getByRole("cell", { name: "Opérations diverses" })).toBeVisible();

  await page.getByRole("button", { name: "Créer un journal" }).click();
  await dialog.getByLabel("Code").fill("OD");
  await dialog.getByLabel("Libellé").fill("Doublon");
  await dialog.getByRole("button", { name: "Créer le journal" }).click();
  await expect(dialog.getByText("Le journal OD existe déjà.")).toBeVisible();
  await dialog.getByRole("button", { name: "Annuler" }).click();
  await expect(dialog).toBeHidden();
});

test("exercices : création, accès à l'assistant de clôture ; adresse du formulaire", async ({ page }) => {
  await login(page, "Association E2E", "/fiscal-years/new");
  const dialog = page.getByRole("dialog", { name: "Créer un exercice" });
  await expect(dialog).toBeVisible();  // ancienne adresse du formulaire : fenêtre ouverte
  await dialog.getByLabel("Libellé").fill("2026");
  await dialog.getByRole("button", { name: "Créer l'exercice" }).click();
  await expect(page.getByText("Exercice « 2026 » créé.")).toBeVisible();

  const row = page.getByRole("row", { name: /2026/ });
  await expect(row.getByText("Ouvert")).toBeVisible();
  await row.getByRole("link", { name: "Clôturer…" }).click();
  await expect(page.getByRole("heading", { name: "Clôture de l'exercice 2026" })).toBeVisible();
  await page.getByRole("button", { name: /6\. Clôture/ }).click();
  await expect(page.getByText("Étapes à terminer avant la clôture")).toBeVisible();
  await expect(page.getByRole("button", { name: "Clôture provisoire" })).toBeDisabled();
});

test("colonnes masquées gardées après reconnexion", async ({ page }) => {
  await login(page, "Association E2E", "/accounts/");
  await expect(page.getByRole("table").getByText("Type", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Colonnes affichées" }).click();
  await page.getByRole("menuitem", { name: "Type" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("table").getByText("Type", { exact: true })).toHaveCount(0);
  await page.waitForTimeout(800);  // préférences envoyées après 500 ms

  await page.getByRole("button", { name: "Menu utilisateur" }).click();
  await page.getByRole("menuitem", { name: "Se déconnecter" }).click();
  await expect(page).toHaveURL(/\/login/);
  await login(page, "Association E2E", "/accounts/");
  await expect(page.getByRole("heading", { name: "Plan comptable" })).toBeVisible();
  await expect(page.getByRole("table").getByText("Type", { exact: true })).toHaveCount(0);
});
