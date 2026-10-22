// Configuration (phase H) : secret d'une intégration jamais réaffiché ; instances et sauvegarde.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test("intégration : un secret enregistré n'est jamais réaffiché", async ({ page }) => {
  await login(page, "Association E2E", "/configuration/integrations/stancer");
  await expect(page.getByRole("heading", { name: "Stancer" })).toBeVisible();
  // Désactivée d'abord : l'enregistrement ne teste pas la connexion (aucun appel à Stancer).
  await page.getByRole("button", { name: "Désactiver" }).click();
  await expect(page.getByText("Intégration Stancer désactivée.")).toBeVisible();
  await page.getByLabel(/Clé secrète/).fill("sk_e2e_tres_secret");
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
  await expect(page.getByText("Configuration Stancer enregistrée (intégration désactivée, non testée).")).toBeVisible();
  await page.reload();
  const secret = page.getByLabel(/Clé secrète/);
  await expect(secret).toHaveValue("");
  await expect(secret).toHaveAttribute("placeholder", "•••••••• (enregistré)");
  await expect(page.getByLabel("Effacer la valeur enregistrée")).toBeVisible();
});

test("instances : liste, fiche et sauvegarde", async ({ page }) => {
  await login(page, "Association E2E", "/instances/");
  await page.getByRole("link", { name: "sci-e2e" }).click();
  await expect(page.getByRole("heading", { name: "SCI E2E" })).toBeVisible();
  await page.getByRole("button", { name: "Créer une sauvegarde" }).click();
  await expect(page.getByText(/Sauvegarde créée : sci-e2e-\d{8}-\d{6}\.zip/)).toBeVisible();
  await page.getByRole("link", { name: "Restaurer un fichier…" }).click();
  const dialog = page.getByRole("dialog", { name: "Restaurer SCI E2E" });
  await expect(dialog.getByRole("button", { name: "Restaurer SCI E2E" })).toBeDisabled();
});
