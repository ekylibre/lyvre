// Utilisateurs et rôles à la création d'une instance (E4) : l'administrateur global crée l'instance
// avec deux nouveaux comptes, retrouve les accès sur la fiche ; le nouvel administrateur doit choisir
// son mot de passe à la première connexion, puis arrive sur l'instance.
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

const PAUL = { email: "paul@membres.test", password: "paul-initial-mdp" };

test("création d'une instance avec ses utilisateurs, mot de passe imposé à la première connexion", async ({ page }) => {
  await login(page, "Association E2E", "/instances/new");
  const dialog = page.getByRole("dialog", { name: "Nouvelle instance" });
  await dialog.getByLabel("Slug").fill("membres-e2e");
  await dialog.getByLabel("Libellé").fill("Asso Membres E2E");
  await dialog.getByText("Base existante").click();
  await dialog.getByLabel("URL de base de données").fill("sqlite:///membres-e2e.db");

  await dialog.getByRole("button", { name: "Ajouter un utilisateur" }).click();
  await dialog.getByText("Nouveau compte", { exact: true }).first().click();
  await dialog.getByRole("textbox", { name: "Email" }).fill(PAUL.email);
  await dialog.getByRole("textbox", { name: "Nom" }).fill("Paul");
  await dialog.getByLabel("Mot de passe initial").fill(PAUL.password);

  await dialog.getByRole("button", { name: "Ajouter un utilisateur" }).click();
  await dialog.getByText("Nouveau compte", { exact: true }).nth(1).click();
  await dialog.getByRole("textbox", { name: "Email" }).nth(1).fill("lea@membres.test");
  await dialog.getByLabel("Mot de passe initial").nth(1).fill("court");
  await dialog.getByRole("button", { name: "Créer l'instance" }).click();
  await expect(dialog.getByText("8 caractères au moins.")).toBeVisible();  // refusé avant l'envoi
  await dialog.getByLabel("Mot de passe initial").nth(1).fill("lea-initial-mdp");
  await dialog.getByRole("button", { name: "Créer l'instance" }).click();
  await expect(page.getByText("Instance « Asso Membres E2E » créée ; 2 comptes créés, 2 accès donnés.")).toBeVisible();

  // Fiche : accès de l'instance, rôle modifiable.
  await page.getByRole("link", { name: "membres-e2e" }).click();
  await expect(page.getByRole("heading", { name: "Accès" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: `Rôle de ${PAUL.email}` })).toHaveValue("Administrateur");
  await expect(page.getByRole("combobox", { name: "Rôle de lea@membres.test" })).toHaveValue("Trésorier");

  // Première connexion de Paul : mot de passe imposé, puis l'instance.
  await page.goto("/logout");
  await page.getByLabel("Email").fill(PAUL.email);
  await page.getByLabel("Mot de passe").fill(PAUL.password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("heading", { name: "Choisissez votre mot de passe" })).toBeVisible();
  await page.goto("/entries/");  // tout le reste renvoie au choix du mot de passe
  await expect(page.getByRole("heading", { name: "Choisissez votre mot de passe" })).toBeVisible();
  await page.getByLabel("Mot de passe actuel").fill(PAUL.password);
  await page.getByLabel("Nouveau mot de passe").fill("paul-choisi-mdp");
  await page.getByLabel("Confirmation").fill("paul-choisi-mdp");
  await page.getByRole("button", { name: "Enregistrer le mot de passe" }).click();
  await expect(page.getByRole("banner")).toContainText("Asso Membres E2E");
});
