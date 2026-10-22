// Parcours tiers (phase C) : créer un tiers (SIRET refusé au champ), ouvrir sa fiche ;
// saisir un temps de travaux ; retrouver un tiers par la palette Ctrl+K.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("tiers : création, erreur de SIRET, fiche", async ({ page }) => {
  await login(page, "Association E2E", "/entities/");
  await page.getByRole("button", { name: "Créer un tiers" }).click();
  const drawer = page.getByRole("dialog", { name: "Créer un tiers" });
  await drawer.getByLabel("Nom").fill("Biocoop du Lez");
  await drawer.getByLabel("SIRET").fill("123");
  await drawer.getByRole("button", { name: "Créer le tiers" }).click();
  await expect(drawer.getByText("Le SIRET doit comporter 14 chiffres.")).toBeVisible();
  await drawer.getByLabel("SIRET").fill("552 081 317 66522");
  await drawer.getByLabel("Bénévole").check();
  await drawer.getByRole("button", { name: "Créer le tiers" }).click();
  await expect(page.getByText("Entité « Biocoop du Lez » créée.")).toBeVisible();

  await page.getByRole("link", { name: "Biocoop du Lez" }).click();
  await expect(page).toHaveURL(/\/entities\/\d+$/);
  await expect(page.getByRole("heading", { name: /Biocoop du Lez/ })).toBeVisible();
  await expect(page.getByText(/SIRET 55208131766522/)).toBeVisible();
  await expect(page.getByText("Aucun temps saisi pour ce bénévole.")).toBeVisible();
});

test("temps de travaux : saisie, total, palette de recherche", async ({ page }) => {
  await login(page, "Association E2E", "/work-times/task-types");
  await page.getByRole("button", { name: "Créer un type" }).click();
  const typeDialog = page.getByRole("dialog", { name: "Créer un type de tâche" });
  await typeDialog.getByLabel("Nom").fill("Caisse");
  await typeDialog.getByLabel("Taux horaire").fill("20");
  await typeDialog.getByRole("button", { name: "Créer le type" }).click();
  await expect(page.getByText("Type de tâche « Caisse » créé.")).toBeVisible();

  await page.goto("/entities/new");
  const drawer = page.getByRole("dialog", { name: "Créer un tiers" });
  await drawer.getByLabel("Nom").fill("Alice Martin");
  await drawer.getByLabel("Bénévole").check();
  await drawer.getByRole("button", { name: "Créer le tiers" }).click();
  await expect(page.getByText("Entité « Alice Martin » créée.")).toBeVisible();

  await page.goto("/work-times/");
  await page.getByRole("button", { name: "Saisir un temps" }).click();
  const dialog = page.getByRole("dialog", { name: "Saisir un temps" });
  await dialog.getByRole("combobox", { name: "Bénévole" }).click();
  await page.getByRole("option", { name: "Alice Martin" }).click();
  await dialog.getByRole("combobox", { name: "Type de tâche" }).click();
  await page.getByRole("option", { name: "Caisse" }).click();
  await dialog.getByLabel("Heures").fill("2,5");
  await dialog.getByRole("button", { name: "Enregistrer le temps" }).click();
  await expect(page.getByText("Temps de travaux enregistré.")).toBeVisible();
  await expect(page.getByText(/1 temps · 2,50 h/)).toBeVisible();
  await expect(page.getByRole("cell", { name: /50,00/ })).toBeVisible();

  await page.keyboard.press("Control+k");
  const search = page.getByPlaceholder(/Aller à un écran/);
  await search.fill("alice");
  await page.getByRole("button", { name: /Alice Martin/ }).click();
  await expect(page).toHaveURL(/\/entities\/\d+$/);
  await expect(page.getByText("Temps de travaux (1)")).toBeVisible();
});
