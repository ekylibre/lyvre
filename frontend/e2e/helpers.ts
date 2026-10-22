import { expect, type Page } from "@playwright/test";
import fixtures from "./fixtures.json" with { type: "json" };

/** Connexion du compte de test, puis choix de l'instance. */
export async function login(page: Page, instance = "Association E2E", next = "/") {
  await page.goto(`/login?next=${encodeURIComponent(next)}`);
  await page.getByLabel("Email").fill(fixtures.user.email);
  await page.getByLabel("Mot de passe").fill(fixtures.user.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL(/\/select-instance/);
  await page.getByLabel(instance).check();
  await page.getByRole("button", { name: "Continuer" }).click();
}
