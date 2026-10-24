// Parcours : connexion, choix d'instance, retour à la page demandée, déconnexion.
import { expect, test } from "@playwright/test";
import fixtures from "./fixtures.json" with { type: "json" };

const { email, password } = fixtures.user;

test("connexion puis choix d'instance et retour à la page demandée", async ({ page }) => {
  await page.goto("/entries/");
  await expect(page).toHaveURL(/\/login\?next=%2Fentries%2F/);

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mot de passe").fill("mauvais");
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("alert")).toHaveText("Email ou mot de passe incorrect.");

  await page.getByLabel("Mot de passe").fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL(/\/select-instance\?next=%2Fentries%2F/);
  await expect(page.getByText(`Connecté en tant que ${email}.`)).toBeVisible();

  await page.getByLabel("SCI E2E").check();
  await page.getByRole("button", { name: "Continuer" }).click();
  await expect(page).toHaveURL(/\/entries\/$/);
  await expect(page.getByRole("heading", { name: "Écritures" })).toBeVisible();
  await expect(page.getByRole("banner")).toContainText("SCI E2E");

  // La page de connexion n'est plus utile une fois connecté.
  await page.goto("/login");
  await expect(page).toHaveURL(/\/$/);

  await page.goto("/logout");
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/select-instance");
  await expect(page).toHaveURL(/\/login\?next=%2Fselect-instance/);
});

test("changer d'instance depuis la page de choix", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Mot de passe").fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await page.getByLabel("Association E2E").check();
  await page.getByRole("button", { name: "Continuer" }).click();
  await expect(page.getByRole("banner")).toContainText("Association E2E");

  await page.goto("/select-instance");
  await expect(page.getByLabel("Association E2E")).toBeChecked();
  await page.getByLabel("SCI E2E").check();
  await page.getByRole("button", { name: "Continuer" }).click();
  await expect(page.getByRole("banner")).toContainText("SCI E2E");
});

test("mot de passe oublié : lien depuis la connexion, demande du lien", async ({ page }) => {
  // Le serveur E2E n'a pas de SMTP : la demande répond comme en production, sans envoi.
  await page.goto("/login");
  await page.getByRole("link", { name: "Mot de passe oublié ?" }).click();
  await expect(page).toHaveURL(/\/password\/forgot$/);
  await page.getByLabel("Email").fill("e2e@example.org");
  await page.getByRole("button", { name: "Recevoir le lien" }).click();
  await expect(page.getByText(/Si un compte correspond à cette adresse/)).toBeVisible();
  await page.getByRole("link", { name: "Retour à la connexion" }).click();
  await expect(page.getByRole("button", { name: "Se connecter" })).toBeVisible();

  await page.goto("/password/reset?token=faux");
  await expect(page.getByText(/invalide, expiré ou a déjà servi/)).toBeVisible();
});
