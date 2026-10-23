// Accès par instance (phase A.1) : l'administrateur donne un accès expert-comptable ; l'expert
// ne voit que cette instance, en lecture seule (interface et API).
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

const EXPERT = { email: "expert@cabinet.test", password: "expert-mot-de-passe" };

test("expert-comptable : accès donné par l'administrateur, lecture seule", async ({ page }) => {
  await login(page, "SCI E2E", "/configuration/access/");
  await expect(page.getByRole("heading", { name: "Accès" })).toBeVisible();
  await page.getByRole("button", { name: "Donner un accès" }).click();
  const dialog = page.getByRole("dialog", { name: "Donner un accès" });
  await dialog.getByLabel("Email").fill(EXPERT.email);
  await dialog.getByLabel("Nom (nouveau compte)").fill("Cabinet Expert");
  await dialog.getByLabel("Mot de passe initial (nouveau compte)").fill(EXPERT.password);
  await dialog.getByRole("button", { name: "Donner l'accès" }).click();
  await expect(page.getByText(`Compte créé et accès donné à ${EXPERT.email} (Expert-comptable).`)).toBeVisible();
  await expect(page.getByRole("combobox", { name: `Rôle de ${EXPERT.email}` })).toHaveValue("Expert-comptable");

  await page.goto("/logout");
  await page.getByLabel("Email").fill(EXPERT.email);
  await page.getByLabel("Mot de passe").fill(EXPERT.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  // Mot de passe initial : à changer avant tout.
  await expect(page.getByRole("heading", { name: "Choisissez votre mot de passe" })).toBeVisible();
  await page.getByLabel("Mot de passe actuel").fill(EXPERT.password);
  await page.getByLabel("Nouveau mot de passe").fill("expert-choisi-mdp");
  await page.getByLabel("Confirmation").fill("expert-choisi-mdp");
  await page.getByRole("button", { name: "Enregistrer le mot de passe" }).click();
  // Une seule instance accessible : choisie d'office.
  await expect(page.getByRole("banner")).toContainText("SCI E2E");
  await expect(page.getByRole("banner")).toContainText("Lecture seule");

  await page.goto("/entries/");
  await expect(page.getByRole("heading", { name: "Écritures" })).toBeVisible();
  await expect(page.getByText("BQ-E2E-1")).toBeVisible();
  await expect(page.getByRole("link", { name: "Saisir une écriture" })).toHaveCount(0);
  await page.goto("/journals/new");
  await expect(page.getByRole("dialog")).toHaveCount(0);  // pas de fenêtre de saisie
  await expect(page.getByRole("button", { name: "Créer un journal" })).toHaveCount(0);
  await page.goto("/entries/new");
  await expect(page.getByText("Accès en lecture seule")).toBeVisible();

  // L'API refuse même une requête forgée.
  const status = await page.evaluate(async () => {
    const session = await (await fetch("/api/v1/session")).json();
    const resp = await fetch("/api/v1/journals", { method: "POST", headers: {
      "Content-Type": "application/json", "X-CSRFToken": session.csrf_token }, body: JSON.stringify({ code: "ZZ", label: "Forgé" }) });
    return resp.status;
  });
  expect(status).toBe(403);
});
